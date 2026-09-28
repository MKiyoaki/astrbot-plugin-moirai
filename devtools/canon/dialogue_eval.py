"""Explicit live dialogue comparisons with source traces and resource measurements."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import resource
import sys
import time


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--conversations", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--code-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--retrieval", choices=("baseline", "hybrid"), default="baseline")
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--token-budget", type=int, default=900)
    parser.add_argument("--temperature", type=float, default=0.3)
    args = parser.parse_args(argv)
    if not args.allow_remote:
        parser.error("Live generation requires --allow-remote")
    if args.out.exists():
        parser.error("Choose a new output path; existing dialogue runs are immutable")
    if args.token_budget < 0:
        parser.error("token-budget must be nonnegative")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(args.code_root.resolve()))
    import run_canon_chat as chat
    from devtools.canon.retrieval import setup

    cases = [json.loads(line) for line in args.conversations.read_text().splitlines() if line.strip()]
    persona = chat.DEFAULT_PERSONA.read_text(encoding="utf-8").strip()
    settings = argparse.Namespace(doctor=True, as_of=None, token_budget=args.token_budget,
                                 top_k=5, evidence_lines=4, show_sources=False, dry_run=False,
                                 temperature=args.temperature, archive_all=False)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "db": str(args.db.resolve()), "retrieval": args.retrieval,
              "code_root": str(args.code_root.resolve()), "token_budget": args.token_budget,
              "temperature": args.temperature, "turns": [],
              "cases_sha256": hashlib.sha256(args.conversations.read_bytes()).hexdigest()}

    def save():
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    calls = []
    request_started = [0.0]

    def on_request(request):
        request_started[0] = time.perf_counter()

    def on_response(response):
        response.read()
        body = json.loads(response.request.content)
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        calls.append({"seconds": time.perf_counter() - request_started[0],
                      "status": response.status_code, "usage": payload.get("usage", {}),
                      "messages": body.get("messages", []),
                      "response": [{"message": {k: v for k, v in item.get("message", {}).items()
                                    if k in ("role", "content", "tool_calls")}}
                                   for item in payload.get("choices", [])]})

    save()
    try:
        with contextlib.ExitStack() as stack:
            retrieval = setup(args.db, None, args.retrieval, stack)[0] if args.retrieval != "baseline" else None
            reader = chat.CanonReader(args.db, retrieval=retrieval)
            stack.callback(reader.close)
            llm = chat.ModelClient(*chat._model_settings("kcl"))
            stack.callback(llm.close)
            llm.client.event_hooks = {"request": [on_request], "response": [on_response]}
            report["model"] = llm.model
            for case in cases:
                session = chat.Session(tools=True)
                session.history = list(case.get("history", []))
                for number, query in enumerate(case["turns"], 1):
                    calls.clear()
                    capture = io.StringIO()
                    started = time.perf_counter()
                    with contextlib.redirect_stdout(capture):
                        chat.run_turn(query, reader=reader, llm=llm, session=session, args=settings,
                                      persona=persona, profile=chat.persona_profile(persona))
                    row = {"case": case["id"], "split": case.get("split", "holdout"),
                           "turn": number, "query": query, "answer": session.history[-1]["content"],
                           "seconds": time.perf_counter() - started,
                           "first_response_seconds": calls[0]["seconds"] if calls else None,
                           "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
                           "calls": list(calls), "trace": capture.getvalue(),
                           "evidence_tokens": (getattr(chat, "estimate_tokens", None)
                                              or chat._estimate_tokens)(session.pack.render()),
                           "evidence": session.pack.render(),
                           "events": [item.event_id for item in session.pack.items],
                           "structural_trace": getattr(reader, "last_expansion_trace", {}),
                           "metrics": getattr(session, "metrics", {})}
                    report["turns"].append(row)
                    save()
                    print(f"{case['id']} {number}: {len(calls)} calls, {row['seconds']:.1f}s", flush=True)
        report["status"] = "complete"
    except Exception as exc:
        report["status"] = "failed"
        report["error_type"] = type(exc).__name__
        raise
    finally:
        save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
