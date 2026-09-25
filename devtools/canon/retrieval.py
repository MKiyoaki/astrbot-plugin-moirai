"""Local experiment commands for canon indexes backed by shared Moirai model providers."""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from core.canon.retrieval import CanonRetrieval
from core.canon.vector_index import VectorIndex, corpus_fingerprint, digest, index_identity, read_documents
from core.retrieval.providers import embedding_identity
from devtools.retrieval import ProviderBridge, development_config


def _meta(path: Path) -> dict:
    try:
        db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    except sqlite3.Error:
        return {}
    try:
        return dict(db.execute("SELECT key,value FROM meta"))
    except sqlite3.Error:
        return {}
    finally:
        db.close()


def build_home(source: Path) -> Path:
    """A chat copy under v<N>/chat/ belongs to the build run it was copied from."""
    if source.parent.name != "chat":
        return source
    meta = _meta(source)
    key = (meta.get("imported_at"), meta.get("prompt_version"))
    if not key[0]:
        return source
    version = source.parent.parent
    runs = [db for pattern in ("*/*/*/canon.sqlite", "*/*/canon.sqlite") for db in version.glob(pattern)
            if "chat" not in db.relative_to(version).parts
            and (_meta(db).get("imported_at"), _meta(db).get("prompt_version")) == key]
    return runs[0] if len(runs) == 1 else source


def retrieval_dir(source: Path) -> Path:
    """Derived indexes and reports live in the build run's folder, never in a shared pool."""
    home = build_home(source)
    return home.parent / f"{home.stem}.retrieval"


def default_index(source: Path, identity: dict) -> Path:
    from core.canon.vector_index import digest
    return retrieval_dir(source) / f"index-{digest(json.dumps(identity, sort_keys=True))[:12]}.sqlite"


def index_available(source: Path, path: Path | None = None) -> bool:
    """Whether the shared embedding is on and this canon DB already has a derived index."""
    try:
        config = development_config()
        identity = index_identity(SimpleNamespace(identity=embedding_identity(config)), "amiya")
        return config.embedding_enabled and (path or default_index(source, identity)).exists()
    except (OSError, ValueError):
        return False


def setup(source: Path, path: Path | None, mode: str, stack: ExitStack, *,
          candidate_limit: int = 40, allow_fallback: bool = False):
    config = development_config()
    if not config.embedding_enabled:
        raise ValueError("The shared Moirai embedding provider is disabled")
    if mode == "hybrid-rerank" and not config.get_rerank_config().enabled:
        raise ValueError("Enable RETRIEVAL_RERANK_ENABLED in the shared development settings")
    identity = index_identity(SimpleNamespace(identity=embedding_identity(config)), "amiya")
    path = path or default_index(source, identity)
    if path.resolve() == source.resolve():
        raise ValueError("The derived index must be separate from the canon database")
    if not path.exists():
        raise ValueError(f"向量索引还没建：{path}\n"
                         f"先运行 moirai canon retrieval build --allow-remote --db {source}")
    index = VectorIndex(path, identity)
    stack.callback(index.close)
    index.validate(read_documents(source))
    bridge = ProviderBridge(config)
    stack.callback(bridge.close)
    retrieval = CanonRetrieval(source, index, bridge, mode=mode, candidate_limit=candidate_limit,
                               allow_fallback=allow_fallback)
    return retrieval, bridge, path


def _rank(ids, expected) -> int | None:
    return next((i for i, eid in enumerate(ids, 1) if eid in expected), None)


def stage_ranks(channels: dict, trace: dict, hits: list, injected: list, expected: set) -> dict:
    """Where the first expected event sits at each retrieval stage (None = dropped there)."""
    ordered = lambda ranks: sorted(ranks, key=ranks.get)
    stages = {"fts": _rank(ordered(channels.get("fts", {})), expected),
              "lines": _rank(ordered(channels.get("lines", {})), expected),
              "entities": _rank(ordered(channels.get("entities", {})), expected)}
    if "dense" in trace:
        stages["dense"] = _rank([eid for eid, _ in trace["dense"]], expected)
    if "candidates" in trace:
        stages["pool"] = _rank([c["event_id"] for c in trace["candidates"]], expected)
    if "reranked" in trace:
        stages["reranked"] = _rank([r["event_id"] for r in trace["reranked"]], expected)
    stages["final"] = _rank(list(dict.fromkeys(hits)), expected)
    stages["injected"] = _rank(injected, expected)
    return stages


def expected_for(case: dict, reader) -> tuple[set[str], list[str]]:
    """Version-independent gold: events of this DB that cover an answer line, and those lines' text."""
    lines = set(case.get("expected_lines") or ())
    if not lines:
        return set(case.get("expected_events") or ()), []
    events = {eid for eid, rows in reader.event_lines.items() if any(key in lines for key, _ in rows)}
    marks = ",".join("?" for _ in lines)
    texts = [row[0] for row in reader.db.execute(f"SELECT text FROM lines WHERE line_key IN ({marks})", tuple(lines))]
    return events, texts


def answer_injected(pack, texts: list[str]) -> bool:
    heads = [text.strip()[:30] for text in texts if text.strip()]
    return any(head and head in text for item in pack.items for _, text in item.lines for head in heads)


def summarize(rows: list[dict]) -> dict:
    scored = [r for r in rows if "stages" in r]
    rate = lambda items, key: round(sum(r["stages"].get(key) is not None for r in items) / len(items), 3) if items else None
    summary = {"questions": len(scored),
               "final_recall": rate(scored, "final"), "injected_recall": rate(scored, "injected"),
               "mrr": round(sum(1 / r["stages"]["final"] for r in scored if r["stages"]["final"]) / len(scored), 3)
               if scored else None,
               "answer_line_injected": round(sum(bool(r.get("answer_line_injected")) for r in scored) / len(scored), 3)
               if scored and any("answer_line_injected" in r for r in scored) else None,
               "stage_recall": {k: rate([r for r in scored if k in r["stages"]], k)
                                for k in ("fts", "lines", "entities", "dense", "pool", "reranked")
                                if any(k in r["stages"] for r in scored)},
               "by_category": {}}
    for category in sorted({r.get("category", "") for r in scored}):
        items = [r for r in scored if r.get("category", "") == category]
        summary["by_category"][category] = {"n": len(items), "final": rate(items, "final"),
                                            "injected": rate(items, "injected")}
    lanes = [r for r in rows if r.get("expected_lane")]
    if lanes:
        summary["lane_accuracy"] = round(sum(r["lane"] == r["expected_lane"] for r in lanes) / len(lanes), 3)
        summary["lane_by_category"] = {
            category: round(sum(r["lane"] == r["expected_lane"] for r in items) / len(items), 3)
            for category in sorted({r.get("category", "") for r in lanes})
            if (items := [r for r in lanes if r.get("category", "") == category])
        }
    labeled = [r for r in rows if "gold_available" in r and "facet_results" not in r]
    summary["unavailable_questions"] = sum(not r["gold_available"] for r in labeled)
    general = [r for r in rows if "facet_results" in r]
    if general:
        eligible = [r for r in general if r["gold_available"]]
        facets = [facet for r in eligible for facet in r["facet_results"]]
        summary["general"] = {
            "questions": len(general), "comparable": len(eligible),
            "partial": sum(any(f["available"] for f in r["facet_results"]) and not r["gold_available"]
                           for r in general),
            "unavailable": sum(not any(f["available"] for f in r["facet_results"]) for r in general),
            "facets": len(facets),
            "final_facet_recall": round(sum(f["final_rank"] is not None for f in facets) / len(facets), 3)
                                  if facets else None,
            "injected_facet_recall": round(sum(f["injected_rank"] is not None for f in facets) / len(facets), 3)
                                     if facets else None,
            "answer_line_facet_rate": round(sum(f["answer_line_injected"] for f in facets) / len(facets), 3)
                                      if facets else None,
            "at_least_two_final": round(sum(sum(f["final_rank"] is not None for f in r["facet_results"]) >= 2
                                            for r in eligible) / len(eligible), 3) if eligible else None,
            "complete_final": round(sum(all(f["final_rank"] is not None for f in r["facet_results"])
                                        for r in eligible) / len(eligible), 3) if eligible else None,
            "lane_accuracy": round(sum(r["lane"] == r.get("expected_lane") for r in eligible) / len(eligible), 3)
                             if eligible else None,
        }
    return summary


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    from run_canon_chat import (DEFAULT_DB, CanonReader, EvidencePack, _estimate_tokens,
                                fill, fill_overview, plan_turn, route)
    parser = argparse.ArgumentParser(description="Canon retrieval experiment; plan is offline")
    parser.add_argument("command", choices=("plan", "build", "probe"))
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--index", type=Path)
    parser.add_argument("--allow-remote", action="store_true", help="Allow billed embedding/rerank requests")
    parser.add_argument("--mode", choices=("baseline", "hybrid", "hybrid-rerank"), default="baseline")
    parser.add_argument("--question", action="append", default=[])
    parser.add_argument("--questions", type=Path, help="Local JSONL with question and optional expected_events")
    parser.add_argument("--out", type=Path, help="Local experiment JSON report")
    parser.add_argument("--allow-fallback", action="store_true")
    parser.add_argument("--candidates", type=int, default=40)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--token-budget", type=int, default=900)
    parser.add_argument("--evidence-lines", type=int, default=4)
    parser.add_argument("--not-doctor", action="store_true")
    parser.add_argument("--pace", type=float, default=0.0,
                        help="Seconds between probe questions, to stay under provider rate limits")
    args = parser.parse_args(argv)
    if args.candidates < 1 or args.top_k < 1 or args.token_budget < 0 or args.evidence_lines < 0:
        parser.error("candidates and top-k must be positive; token-budget and evidence-lines cannot be negative")
    if (args.command == "build" or args.command == "probe" and args.mode != "baseline") and not args.allow_remote:
        parser.error("This operation calls remote models; pass --allow-remote (plan/baseline remain offline)")
    config = development_config()
    embed_cfg = config.get_embedding_config()
    identity = index_identity(SimpleNamespace(identity=embedding_identity(config)), "amiya")
    path = args.index or default_index(args.db, identity)
    if path.resolve() == args.db.resolve():
        parser.error("--index must differ from --db")
    documents = read_documents(args.db)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = args.out or retrieval_dir(args.db) / "runs" / f"{stamp}-{args.command}-{args.mode}.json"
    if out.resolve() in {args.db.resolve(), path.resolve()}:
        parser.error("--out cannot overwrite an input database")
    report = {"status": "started", "command": args.command, "mode": args.mode,
              "source": str(args.db.resolve()), "index": str(path.resolve()),
              "identity": identity, "corpus": corpus_fingerprint(documents),
              "events": len(documents), "question_results": [],
              "settings": {"candidate_limit": args.candidates, "top_k": args.top_k,
                           "token_budget": args.token_budget, "evidence_lines": args.evidence_lines,
                           "doctor": not args.not_doctor, "allow_fallback": args.allow_fallback,
                           "request_batch_size": embed_cfg.request_batch_size,
                           "concurrency": embed_cfg.concurrency}}
    write_report = True
    with ExitStack() as stack:
        if args.command == "plan":
            missing = documents
            if path.exists():
                index = VectorIndex(path, identity)
                stack.callback(index.close)
                missing = index.missing(documents)
            print(json.dumps({"events": len(documents), "uncached_documents": len(missing),
                              "input_characters": sum(len(d.text) for d in missing),
                              "estimated_batches": math.ceil(len(missing) / embed_cfg.request_batch_size),
                              "batch_size": embed_cfg.request_batch_size,
                              "concurrency": embed_cfg.concurrency, "index": str(path),
                              "model": embed_cfg.model}, ensure_ascii=False, indent=2))
            return 0
        bridge = None
        try:
            if args.command == "build":
                if not config.embedding_enabled:
                    raise ValueError("Shared embedding provider is disabled")
                index = VectorIndex(path, identity, writable=True)
                stack.callback(index.close)
                bridge = ProviderBridge(config)
                stack.callback(bridge.close)
                report["build"] = index.build(
                    documents, bridge, batch_size=embed_cfg.request_batch_size,
                    concurrency=embed_cfg.concurrency,
                    progress=lambda done, total: print(f"[vectors] {done}/{total}", flush=True),
                )
            else:
                retrieval = None
                if args.mode != "baseline":
                    retrieval, bridge, path = setup(args.db, path, args.mode, stack,
                                                    candidate_limit=args.candidates,
                                                    allow_fallback=args.allow_fallback)
                reader = CanonReader(args.db, retrieval=retrieval)
                stack.callback(reader.close)
                cases = [{"question": q} for q in args.question]
                if args.questions:
                    cases.extend(json.loads(line) for line in args.questions.read_text().splitlines() if line.strip())
                if not cases:
                    raise ValueError("Supply --question or --questions for a retrieval probe")
                case_digest = digest(json.dumps(cases, ensure_ascii=False, sort_keys=True))
                report["question_digest"] = case_digest
                if args.out is not None and out.is_file():
                    try:
                        prior = json.loads(out.read_text())
                    except (OSError, ValueError) as exc:
                        write_report = False
                        raise ValueError("--out exists but is not a readable retrieval report") from exc
                    if not isinstance(prior, dict):
                        write_report = False
                        raise ValueError("--out exists but is not a retrieval report")
                    kept = prior.get("question_results", [])
                    compatible = (
                        prior.get("command") == report["command"]
                        and prior.get("mode") == report["mode"]
                        and prior.get("corpus") == report["corpus"]
                        and prior.get("identity") == identity
                        and prior.get("settings") == report["settings"]
                        and isinstance(kept, list)
                        and prior.get("question_digest") == case_digest
                    )
                    if not compatible:
                        write_report = False
                        raise ValueError("--out exists with a different corpus, question bank or probe settings")
                    kept = [row for row in kept if isinstance(row, dict) and row.get("id")]
                    if kept:
                        answered = {row["id"] for row in kept}
                        report["question_results"] = kept
                        cases = [case for case in cases if case.get("id") not in answered]
                        print(f"[retrieval] resume: {len(answered)} answered kept, {len(cases)} left")
                        if not cases and prior.get("status") == "complete":
                            write_report = False
                            return 0
                for number, case in enumerate(cases):
                    if number and args.pace > 0 and retrieval is not None:
                        time.sleep(args.pace)
                    question = case["question"]
                    doctor = not args.not_doctor
                    plan = route(reader, plan_turn(reader, question, None, None), question, doctor)
                    pack = EvidencePack("对方（博士）" if doctor else "博士", doctor)
                    all_hits = []
                    overview_trace = None
                    if plan.overview:
                        all_hits, overview_trace = reader.overview_search(
                            plan.search_query, doctor=doctor,
                            evidence_lines=min(2, args.evidence_lines))
                        fill_overview(pack, all_hits, args.token_budget)
                    else:
                        subjects = plan.subjects if len(plan.subjects) > 1 else (None,)
                        for subject in subjects:
                            hits, episode = reader.search(plan.search_query, top_k=args.top_k,
                                                           evidence_lines=args.evidence_lines, doctor=doctor,
                                                           focus_person=subject)
                            all_hits.extend(hits)
                            if plan.lane != "chat":
                                fill(pack, hits, episode, args.token_budget // len(subjects),
                                     total_budget=args.token_budget)
                    trace = retrieval.last_trace if retrieval else {"mode": "baseline"}
                    row = {**{k: case[k] for k in ("id", "category", "expected_lane") if k in case},
                           "question": question, "lane": plan.lane, "overview": plan.overview,
                           "overview_trace": overview_trace,
                           "evidence_tokens": _estimate_tokens(pack.render()),
                           "hits": [{"event_id": h.event_id, "score": h.score, "channel": h.channel}
                                    for h in all_hits],
                           "injected_events": [m.event_id for m in pack.items], "trace": trace}
                    if "facets" in case:
                        facets = []
                        for facet in case["facets"]:
                            expected, answer_texts = expected_for(facet, reader)
                            ranks = stage_ranks(reader.last_channels, trace,
                                                [h.event_id for h in all_hits],
                                                row["injected_events"], expected) if expected else {}
                            facets.append({"id": facet["id"], "note": facet.get("note", ""),
                                           "available": bool(expected), "expected_events": sorted(expected),
                                           "final_rank": ranks.get("final"),
                                           "injected_rank": ranks.get("injected"),
                                           "answer_line_injected": answer_injected(pack, answer_texts)
                                           if expected and answer_texts else False})
                        row["facet_results"] = facets
                        row["gold_available"] = bool(facets) and all(f["available"] for f in facets)
                    else:
                        expected, answer_texts = expected_for(case, reader)
                        if case.get("expected_lines") or case.get("expected_events"):
                            row["gold_available"] = bool(expected)
                        if expected:
                            row["expected_events"] = sorted(expected)
                            row["stages"] = stage_ranks(reader.last_channels, trace,
                                                        [h.event_id for h in all_hits],
                                                        row["injected_events"], expected)
                            if answer_texts:
                                row["answer_line_injected"] = answer_injected(pack, answer_texts)
                    report["question_results"].append(row)
                    _write(out, report)
                    stages = row.get("stages", {})
                    if "facet_results" in row:
                        detail = "facets=" + "/".join(
                            str(f["final_rank"] if f["final_rank"] is not None else "·")
                            for f in row["facet_results"])
                    else:
                        detail = " ".join(f"{k}={v if v is not None else '·'}" for k, v in stages.items())
                    print(f"{case.get('id', '-'):4} {plan.lane:6} {detail}  {question}", flush=True)
                report["summary"] = summarize(report["question_results"])
                print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
            report["status"] = "complete"
        except BaseException as exc:
            report.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
                          error=str(exc) if isinstance(exc, (ValueError, RuntimeError)) else type(exc).__name__)
            raise
        finally:
            if write_report:
                report["metrics"] = bridge.metrics() if bridge else {}
                _write(out, report)
                print(f"[retrieval] report: {out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, sqlite3.Error, ValueError, RuntimeError) as exc:
        print(f"[retrieval] {exc}", file=sys.stderr)
        raise SystemExit(1)
