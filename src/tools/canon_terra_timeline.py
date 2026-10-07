"""Parse a locally saved PRTS 泰拉年表 page into timeline entries for `canon calendar-apply`.

The page is CC BY-NC-SA third-party content saved by the user; the page and its parsed entries stay in
`.dev_data/` and are never committed. Only the era heading, time label and cited story links matter to the
calendar; the entry text is kept for matching recounted events and never reaches the model.
"""
from __future__ import annotations

import argparse
import html
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / ".dev_data/canon/timeline"
SOURCE = "https://prts.wiki/w/泰拉年表"
LICENSE = "CC BY-NC-SA 3.0 (PRTS); local reference only, do not commit"


def clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", fragment))).strip()


def parse(page: str) -> list[dict]:
    tokens = [(m.start(), "heading", m) for m in re.finditer(r"<h([234])[^>]*>(.*?)</h\1>", page, re.S)]
    tokens += [(m.start(), "table", m) for m in re.finditer(r"<table.*?</table>", page, re.S)]
    headings: dict[str, str] = {}
    entries = []
    for _, kind, match in sorted(tokens, key=lambda token: token[0]):
        if kind == "heading":
            headings[match.group(1)] = clean(match.group(2))
            for deeper in ("3", "4"):
                if deeper > match.group(1):
                    headings.pop(deeper, None)
            continue
        label = None
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", match.group(0), re.S):
            if header := re.search(r"<th[^>]*>(.*?)</th>", row, re.S):
                label = clean(header.group(1))
            for cell in re.findall(r"<td[^>]*>(.*)</td>", row, re.S):
                body = re.sub(r'<div class="mw-collapsible-content".*', "", cell, flags=re.S)
                text = clean(re.sub(r"<button.*?</button>", "", body, flags=re.S))
                sources = [{"label": clean(item), "urls": re.findall(r'href="(https://prts\.wiki/w/[^"]+)"', item)}
                           for item in re.findall(r"<li>(.*?)</li>", cell, re.S)]
                if text:
                    entries.append({"section": " / ".join(headings[level] for level in sorted(headings)),
                                    "time": label, "text": text, "sources": sources})
    return entries


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PRTS 泰拉年表 HTML → canon calendar entries (local only)")
    parser.add_argument("--html", type=Path, default=FOLDER / "prts-terra-timeline.html")
    parser.add_argument("--out", type=Path, default=FOLDER / "prts-terra-timeline.json")
    parser.add_argument("--saved", default="", help="When and how the page was saved, recorded with the entries")
    args = parser.parse_args(argv)
    entries = parse(args.html.read_text(encoding="utf-8", errors="replace"))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"source": SOURCE, "license": LICENSE, "saved": args.saved, "entries": entries},
                                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(entries)} entries, {sum(bool(entry['sources']) for entry in entries)} with sources → {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
