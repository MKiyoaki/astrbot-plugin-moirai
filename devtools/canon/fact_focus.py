"""核心角色窄范围时间事实审阅：从全量审阅包切子包并生成原对照勾选页。"""
from __future__ import annotations

import argparse
import html
import json
import sqlite3
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parents[2]))

from run_canon_chat import DEFAULT_DB

DOCTOR_TOKEN = "{DOCTOR}"
PREDICATE_LABEL = {
    "location": "所在位置",
    "affiliation": "组织归属",
    "life_status": "存活状态",
    "custody": "拘押关系",
}
CORE_SUBJECTS = ("阿米娅", "博士", "凯尔希")


def default_review(db_path: Path) -> Path:
    runs = sorted(db_path.parent.glob("facts-candidates-*.review.json"))
    if not runs:
        raise SystemExit(f"{db_path.parent} 下没有 facts-candidates-*.review.json")
    return runs[-1]


def focus_bundle(bundle: dict, subjects: list[str]) -> dict:
    names = set(subjects)
    if "博士" in names:
        names.add(DOCTOR_TOKEN)
    facts = []
    for fact in bundle["facts"]:
        fact = dict(fact)
        if fact["subject"] == DOCTOR_TOKEN:
            fact["subject"] = "博士"
        if fact["subject"] in names:
            facts.append(fact)
    if not facts:
        raise SystemExit(f"审阅包中没有这些主体的事实：{subjects}")
    used = {f["point_id"] for f in facts}
    points = [dict(p) for p in bundle["points"] if p["point_id"] in used]
    groups: dict[tuple[str, str], list[dict]] = {}
    for fact in facts:
        groups.setdefault((fact["subject"], fact["predicate"]), []).append(fact)
    review_groups = []
    for (subject, predicate), items in sorted(groups.items()):
        review_groups.append({
            "subject": subject, "predicate": predicate,
            "objects": sorted({f["object"] for f in items}), "fact_ids": [f["fact_id"] for f in items],
            "needs_timeline_review": len({f["object"] for f in items}) > 1,
        })
    return {"format": "canon-fact-review-v1", "points": points,
            "before": [], "facts": facts, "transitions": [], "coverage": [],
            "review_groups": review_groups, "instructions": bundle.get("instructions", "")}


def order_key(point: dict, scene_pos: dict[str, float]) -> tuple[float, str]:
    return (scene_pos.get(point.get("scene_key") or "", 1e18), point.get("label") or "")


def evidence_texts(db_path: Path, facts: list[dict]) -> dict[str, dict]:
    uri = db_path.resolve().as_uri() + "?mode=ro"
    db = sqlite3.connect(uri, uri=True)
    db.row_factory = sqlite3.Row
    try:
        scene_pos = {row["scene_key"]: row["narrative_pos"] for row in
                     db.execute("SELECT scene_key,narrative_pos FROM scenes")}
        lines = {}
        for ids in {ev["line_key"] for f in facts for ev in f["evidence"]}:
            row = db.execute(
                "SELECT l.speaker,l.text,s.anchor,l.scene_key FROM lines l "
                "JOIN scenes s ON s.scene_key=l.scene_key WHERE l.line_key=?", (ids,)).fetchone()
            if row:
                lines[ids] = dict(row)
        return {"lines": lines, "scene_pos": scene_pos}
    finally:
        db.close()


PAGE = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>时间事实窄范围审阅</title>
<style>
body{font:14px/1.55 system-ui,"Segoe UI","Noto Sans CJK SC",sans-serif;color:#202a36;background:#f3f5f8;margin:0}
header{position:sticky;top:0;z-index:5;background:#fff;border-bottom:1px solid #dce2ea;padding:12px 20px;display:flex;gap:14px;align-items:center;flex-wrap:wrap;box-shadow:0 2px 10px #1d2e4410}
h1{font-size:16px;margin:0}.hintline{color:#687587;font-size:12px;flex:1}
.bar button{border:1px solid #bdc8d5;background:#fff;border-radius:8px;padding:8px 12px;cursor:pointer}
.bar button:hover{background:#edf3f9}
main{padding:16px 20px 48px;max-width:980px;margin:0 auto}
.subject{background:#fff;border:1px solid #dce2ea;border-radius:10px;padding:14px 18px;margin:14px 0}
.subject>h2{font-size:17px;margin:0 0 4px}
.subject>p{color:#687587;font-size:12px;margin:0 0 10px}
.group h3{font-size:13px;color:#34465b;margin:14px 0 6px;border-bottom:1px solid #e7ebf0;padding-bottom:4px}
.fact{display:grid;grid-template-columns:auto 1fr;gap:4px 10px;padding:8px 6px 8px 2px;border-left:3px solid transparent}
.fact:hover{background:#f8fafc}
.fact input{grid-row:span 2;margin-top:3px}
.fact .claim{font-weight:600;overflow-wrap:anywhere}
.fact .ev{color:#566579;font-size:12.5px}
.bad-ref{color:#b42318}
#out{width:100%;height:110px;margin-top:10px;display:none;font:11px/1.4 monospace}
.clashes .claim{color:#8d591a}
</style></head><body>
<header><h1>时间事实窄范围审阅</h1><span class="hintline">逐条核对下面的原文行；只勾选「原文明确写明」的事实。带冲突标色的是同一本体有多个互相冲突记录的组，需要格外当心；先后关系和状态变更请另行填写，本页不负责。</span>
<div class="bar"><button id="export">生成已审阅包</button><button id="copy">复制 JSON</button></div></header>
<main><!--BODY--><textarea id="out" aria-label="已审阅包 JSON"></textarea></main>
<script>
const DATA = /*DATA*/;
const out = document.getElementById('out');
document.getElementById('export').onclick = () => {
  const checked = [...document.querySelectorAll('input:checked')].map(i => DATA.fact_map[i.value]);
  const used = {};
  checked.forEach(f => { used[f.point_id] = DATA.points[f.point_id]; });
  const bundle = {format: 'canon-fact-review-v1', points: Object.values(used).filter(Boolean),
    before: [], transitions: [], coverage: [],
    facts: checked.map(f => ({...f, source_type: 'explicit', review_status: 'reviewed'})),
    review_groups: [], instructions: ''};
  out.style.display = 'block';
  out.value = JSON.stringify(bundle, null, 2);
};
document.getElementById('copy').onclick = async () => {
  if (!out.value) document.getElementById('export').click();
  try { await navigator.clipboard.writeText(out.value); } catch (e) { out.select(); document.execCommand('copy'); }
};
</script></body></html>"""


def render_page(bundle: dict, aux: dict) -> str:
    pid_to_point = {p["point_id"]: p for p in bundle["points"]}
    clash = {(g["subject"], g["predicate"]) for g in bundle["review_groups"] if g["needs_timeline_review"]}
    sections = []
    for subject in sorted({f["subject"] for f in bundle["facts"]}):
        facts = [f for f in bundle["facts"] if f["subject"] == subject]
        sections.append((subject, facts))
    parts = []
    for subject, facts in sections:
        rows = [f'<h2>{html.escape(subject)}</h2><p>{len(facts)} 条候选。原文行格式：行号 · 说话人：内容。</p>']
        for predicate in sorted({f["predicate"] for f in facts}):
            group = [f for f in facts if f["predicate"] == predicate]
            group.sort(key=lambda f: order_key(pid_to_point[f["point_id"]], aux["scene_pos"]))
            classes = "group clashes" if (subject, predicate) in clash else "group"
            rows.append(f'<div class="{classes}"><h3>{html.escape(PREDICATE_LABEL.get(predicate, predicate))}'
                        f' · {len(group)} 条</h3>')
            for fact in group:
                point = pid_to_point[fact["point_id"]]
                label = f'{html.escape(point.get("label") or "")} · {html.escape(fact.get("polarity") and "肯定" or "否定")}'
                evs = []
                for ev in fact["evidence"]:
                    line = aux["lines"].get(ev["line_key"])
                    if line:
                        evs.append(f'{html.escape(point["scene_key"])} {line["anchor"]} · '
                                   f'{html.escape(line["speaker"] or "旁白")}：{html.escape(line["text"])}')
                    else:
                        evs.append(f'<span class="bad-ref">行 {html.escape(ev["line_key"])} 缺失</span>')
                rows.append(
                    f'<div class="fact"><input type="checkbox" id="c{html.escape(fact["fact_id"])}" '
                    f'value="{html.escape(fact["fact_id"])}">'
                    f'<div class="claim">{html.escape(fact["object"])}（{label}）</div>'
                    f'<div class="ev">{"；".join(evs)}</div></div>')
            rows.append('</div>')
        parts.append(f'<section class="subject">{"".join(rows)}</section>')
    data = {"fact_map": {f["fact_id"]: f for f in bundle["facts"]}, "points": {p["point_id"]: p for p in bundle["points"]}}
    return PAGE.replace("<!--BODY-->", "".join(parts)).replace("/*DATA*/", json.dumps(data, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="从全量时间事实审阅包切出核心角色子包与审阅页")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--review", type=Path, help="默认取 db 同目录最新的 facts-candidates-*.review.json")
    parser.add_argument("--subjects", default=",".join(CORE_SUBJECTS), help="審閱主体，逗号分隔")
    parser.add_argument("--out-dir", type=Path, help="输出目录；默认审阅包所在目录")
    args = parser.parse_args(argv)
    review = args.review or default_review(args.db)
    subjects = [s.strip() for s in args.subjects.split(",") if s.strip()]
    bundle = json.loads(review.read_text(encoding="utf-8"))
    focused = focus_bundle(bundle, subjects)
    aux = evidence_texts(args.db, focused["facts"])
    out_dir = args.out_dir or review.parent
    stem = review.stem.replace(".review", "") + "-focus-" + "-".join(subjects)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"{stem}.json"
    html_path = out_dir / f"{stem}.html"
    json_path.write_text(json.dumps(focused, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(render_page(focused, aux), encoding="utf-8")
    print(f"主体：{'、'.join(subjects)}；候选 {len(focused['facts'])} 条（全包 {len(bundle['facts'])} 条），"
          f"冲突组 {sum(g['needs_timeline_review'] for g in focused['review_groups'])} 个")
    print(f"子包：{json_path}")
    print(f"审阅页：{html_path}")
    print("审阅后：python -m core.canon.cli facts-apply --db <数据库> --input <导出的已审阅包>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
