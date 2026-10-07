"""Run one code tree's own budget_sweep with an extra rubric for cross-chapter causal questions and a judge skip list.

usage: python sweep_wrap.py --tree TREE [--skip-judge g04] -- budget_sweep arguments (--bank --budgets --out ...)
Only questions of kind "cross" get the extra rubric (causal links need evidence, order must follow the story) and an
order_ok field; every other question is judged by the tree's unchanged judge. Skipped ids get a score-less judged row so the
judge never waits on them; the compare script leaves score-less rows out.
"""
import argparse
import hashlib
import importlib.util
import json
import re
import threading
import time
from pathlib import Path

EXTRA = (
    "\n补充规则（只适用于 kind 为 cross 的因果链或跨章节题）：\n"
    "6. 回复里的因果说法（因为、所以、导致、正是……才……）：两头的事都要在材料里有依据；因果连接本身在材料里找不到、却被说成事实的，记入 unsupported；"
    "与材料相反的因果，算幻觉。明确写成她自己的判断（如“在我看来”“我觉得”）且两头有依据的，不算问题。\n"
    "7. 先后：回复里讲的先后与材料里的发生先后相反的，算幻觉；材料没写清先后的，不扣分。\n"
    "8. 题目要求区分必要条件与过程时：把答案要点里的必要条件说成“只是过程中发生的事”，或把过程说成必要条件，按未命中该要点处理。\n"
    "在同一个 JSON 里多加一个字段 order_ok：回复讲了先后且都对为 true，有颠倒为 false，没讲先后为 null。"
)
ORDER = re.compile(r'"order_ok"\s*:\s*(true|false|null)')


def patch(bs):
    original = bs.judge
    local = threading.local()

    class Proxy:
        def __init__(self, llm):
            self.llm = llm

        def complete(self, messages, temperature):
            messages = [{**messages[0], "content": messages[0]["content"] + EXTRA}] + list(messages[1:])
            local.raw = self.llm.complete(messages, temperature)
            return local.raw

    failed = set()

    def judge(llm, case, answer, evidence):
        if case["id"] in failed:
            raise RuntimeError("fast-fail: this question already timed out once in this run")
        try:
            if case.get("kind") != "cross":
                return original(llm, case, answer, evidence)
            verdict = original(Proxy(llm), case, answer, evidence)
        except Exception as exc:
            if any(word in str(exc).lower() for word in ("timed out", "timeout", "502")):
                failed.add(case["id"])
            raise
        found = ORDER.search(getattr(local, "raw", "") or "")
        verdict["order_ok"] = {"true": True, "false": False, "null": None}[found.group(1)] if found else None
        return verdict

    bs.judge = judge
    return bs


def load_tree(tree: Path):
    path = tree / "src/core_eval/canon/budget_sweep.py"
    if not path.is_file():
        path = tree / "devtools/canon/budget_sweep.py"
    spec = importlib.util.spec_from_file_location("budget_sweep_tree", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tree", type=Path, required=True)
    parser.add_argument("--skip-judge", default="g04")
    parser.add_argument("--judge-provider", default=None, help="model family from configs/models (e.g. deepseek, openai) used for the judge phase")
    parser.add_argument("--model-provider", default=None, help="model family from configs/models (e.g. openai) used for the tested model in the run phase")
    args, rest = parser.parse_known_args()
    inner = argparse.ArgumentParser(add_help=False)
    inner.add_argument("--out", type=Path, required=True)
    inner.add_argument("--bank", type=Path)
    inner.add_argument("--budgets", default="2000")
    known, _ = inner.parse_known_args(rest)
    tree = args.tree.resolve()
    bs = patch(load_tree(tree))
    if args.judge_provider or args.model_provider:
        import sys
        if (tree / "src" / "core").is_dir():
            sys.path.insert(0, str(tree / "src"))
            from tools import canon_chat as chat
        else:
            sys.argv = ["run_canon_dev.py"]
            sys.path.insert(0, str(tree))
            import run_canon_dev  # noqa: F401  (loads run_config before the canon modules)
            import run_canon_chat as chat
        real = chat._model_settings

        def settings(model_type=None):
            if model_type == "kcl":
                provider = args.judge_provider if sys._getframe(1).f_code.co_name == "judge_rows" else args.model_provider
                if provider:
                    return real(provider)
            return real(model_type)

        chat._model_settings = settings
    known.out.parent.mkdir(parents=True, exist_ok=True)
    judged = known.out.with_suffix(".judged.jsonl")
    seeded = {(row["id"], row["budget"]) for row in bs.read_rows(judged)}
    for case_id in filter(None, args.skip_judge.split(",")):
        for budget in (int(v) for v in known.budgets.split(",") if v.strip()):
            if (case_id, budget) not in seeded:
                with judged.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps({"id": case_id, "budget": budget, "score": None, "hallucinated": None,
                                             "reason": "judge skipped: timed out in every earlier run"}, ensure_ascii=False) + "\n")
    version = next((line.split(":", 1)[1].strip() for line in (tree / "metadata.yaml").read_text(encoding="utf-8").splitlines()
                    if line.startswith("version")), "?")
    meta = {"tree": str(tree), "version": version, "bank": str(known.bank), "budgets": known.budgets,
            "bank_sha256": hashlib.sha256(known.bank.read_bytes()).hexdigest() if known.bank else None,
            "skip_judge": args.skip_judge, "started": time.strftime("%Y-%m-%d %H:%M:%S"), "argv": rest}
    judging = "--phase" in rest and rest[rest.index("--phase") + 1] == "judge"
    meta["judge_provider"], meta["model_provider"] = args.judge_provider, args.model_provider
    known.out.with_suffix(".judge-meta.json" if judging else ".meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    return bs.main(rest)


if __name__ == "__main__":
    raise SystemExit(main())
