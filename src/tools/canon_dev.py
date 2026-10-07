"""canon 抽取基准的开发工具：用 configs/ 选中的模型手动跑基准、裁判和对比，实时显示进度。

用法（在插件根目录下；也可以经 src/main.py experiments=canon_build / canon_bench / canon_judge 调用）：
    python src/tools/canon_dev.py                          # 列出已有的运行（同 list）
    python src/tools/canon_dev.py estimate [20|100|all]    # 估算调用次数和输入量，不调用接口
    python src/tools/canon_dev.py build                   # 全库续跑事件与事实候选，写出 HTML 审阅页
    python src/tools/canon_dev.py run [20|100|all]         # 事件基准 + 时间事实候选，开始前会确认；样本默认 configs/data 的 samples
    python src/tools/canon_dev.py run 20 --replay pilot    # 回放 v1 试跑，零成本走一遍完整路径
    python src/tools/canon_dev.py run --repeats 3          # 同一配置跑 3 次，报告重测信度
    python src/tools/canon_dev.py run --scene <scene_key>  # 只跑指定的场景（可重复）
    python src/tools/canon_dev.py judge [运行]              # LLM 裁判，默认最近一次真实接口的运行
    python src/tools/canon_dev.py compare <运行> <运行> [...]
    python src/tools/canon_dev.py test                     # 优先只读 v10 全量库试聊；对话只保存在内存
    python src/tools/canon_dev.py open [运行] [--report]    # 用浏览器打开审阅页（--report 打开 report.md）

样本就是 story_pack/samples/ 里的场景清单（Arknights-Texts 的 config/samples.json 定义）：20 是分层抽样，
100 是整块连贯的章节和活动，all 是全部场景；也可以用 --scenes 指定别的清单文件。

<运行> 可以写运行目录名、名字里的一段、路径，或者 latest / latest-api / latest-replay；
回放来源、基线和 compare 还可以写 pilot（v1 的 Luna 试跑）。

模型：沿用 configs/ 选中的 models（lmstudio / deepseek / kcl / openai）和对应的地址、模型名，key 取自环境变量；
canon_tools.model_type、canon_tools.judge_model_type 可以单独指定抽取和裁判用哪一个家族。
其余设置见 configs/canon_tools/default.yaml 与 configs/data/。

数据：全部在 .dev_data/canon/ 下（整个 .dev_data/ 已被 .gitignore 忽略），含剧情原文，只能留在本机。
    v<N>/<样本>/api/       抽取 prompt v<N> 在这个样本上的真实接口运行（样本：20、100、all 或清单名）
    v<N>/<样本>/replay/    回放的运行；放在被回放数据所属的版本下
    v<N>/<样本>/repeats/   --repeats 的一组运行，外加 stability.md
    v<N>/all/build/        build 的全库数据库和时间事实候选
    v<N>/sources/          外部模型（subagent）的原始输出，供回放
    v<N>/chat/             旧试聊数据库副本（可通过 moirai canon test --db 指定）
    compare/               compare 的结果
    logs/                  中断或出错的运行留下的控制台日志（正常结束的日志在运行目录的 console.log）
每个运行目录里有 report.md、summary.json、results.jsonl、review.html、canon.sqlite、console.log；
校验不通过时有 failures/，跑过裁判还有 judge.jsonl 和 judge.log。

控制：Ctrl+C 中断。已经花掉的调用不会重放；没跑完的运行在 list 里标为"未完成"。
"""

import argparse
import asyncio
import datetime
import json
import logging
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import webbrowser
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from core.utils.config_utils import legacy_settings

try:
    _rc = legacy_settings()
    print("[Config] 已组合 configs/")
except Exception as _cfg_err:
    _rc = None
    print(f"[Config] WARNING: configs/ 组合失败（{_cfg_err!r}），只能用 list / estimate / 回放。")
from tools import canon_data as canon_cli
from core_eval.canon.bench import (
    bench_dir,
    error_kind,
    estimate,
    find_character,
    load_replay,
    replay_answers,
    ReplayServer,
    run_bench,
    slug,
    version_tag,
    write_fact_summary,
)
from core_eval.canon.constant_utils import RETRY_MARK
from core_eval.canon.compare import load_results, stability
from core.canon.builder.importer import Importer, load_pack
from core_eval.canon.probes import load_probes
from core.utils.prompts.prompt_canon_utils import PROMPT_VERSION
from core.utils.llm import SimpleLLMClient

# ── Config ────────────────────────────────────────────────────────────────────

def _cfg(name: str, default):
    value = getattr(_rc, name, None) if _rc else None
    return default if value in (None, "") else value


ROOT = _SRC.parent
CANON_DATA = ROOT / ".dev_data" / "canon"
LOGS = CANON_DATA / "logs"
COMPARE = CANON_DATA / "compare"
VERSION = version_tag(PROMPT_VERSION)
PILOT = CANON_DATA / "v1" / "sources" / "luna-pilot"
RUN_MODES = ("api", "replay", "repeats")
PACK = (ROOT / _cfg("CANON_PACK", "../Arknights-Texts/exports/story_pack")).resolve()
PROBES = (ROOT / _cfg("CANON_PROBES", "../Arknights-Texts/eval/canon_extract_probes.jsonl")).resolve()
SCENES = str(_cfg("CANON_SCENES", "20"))
CHARACTER = _cfg("CANON_CHARACTER", "amiya")
CONCURRENCY = int(_cfg("CANON_CONCURRENCY", _cfg("LLM_CONCURRENCY", 2)))
TIMEOUT = float(_cfg("CANON_TIMEOUT", _cfg("TIMEOUT", 300.0)))
BASELINE = _cfg("CANON_BASELINE", "")
_PRICE_IN, _PRICE_OUT = _cfg("CANON_PRICE_IN", None), _cfg("CANON_PRICE_OUT", None)
PRICES = (float(_PRICE_IN), float(_PRICE_OUT)) if _PRICE_IN is not None and _PRICE_OUT is not None else None
MODEL_TYPES = ("lmstudio", "deepseek", "kcl", "openai", "oai")
_PLACEHOLDER_KEYS = {"your_deepseek_api_key_here", "your_openai_api_key_here"}
_INTERRUPTED: list[str] = []


def _model_type(override: str | None, *names: str) -> str:
    chosen = next((v for v in (override, *(_cfg(n, "") for n in names)) if v), "lmstudio")
    return {"oai": "openai"}.get(chosen, chosen)


def _model_info(model_type: str) -> tuple[str, str, str]:
    """按模型类型从 configs/ 取接口地址、key 和模型名。"""
    if model_type == "lmstudio":
        url, key, model = _cfg("LMSTUDIO_API_URL", "http://localhost:1234/v1"), "lm-studio", _cfg("LMSTUDIO_MODEL", "")
    elif model_type == "deepseek":
        url, key, model = "https://api.deepseek.com", _cfg("DEEPSEEK_API_KEY", ""), _cfg("DEEPSEEK_MODEL", "")
    elif model_type == "kcl":
        url = _cfg("KCL_API_URL", "https://ai.create.kcl.ac.uk/api/v1")
        key, model = _cfg("KCL_API_KEY", ""), _cfg("KCL_MODEL", "")
    elif model_type == "openai":
        url = _cfg("OPENAI_API_URL", "https://api.openai.com/v1")
        key, model = _cfg("OPENAI_API_KEY", ""), _cfg("OPENAI_MODEL", "")
    else:
        raise SystemExit(f"不支持的模型类型 {model_type!r}，只能是 {' / '.join(MODEL_TYPES)}")
    if not key or key in _PLACEHOLDER_KEYS:
        raise SystemExit(f"{model_type} 的 API key 没有设置：见 configs/models/ 里该模型文件 api_key_env 指定的环境变量")
    if not model:
        raise SystemExit(f"{model_type} 的模型名没有设置：见 configs/models/")
    return url, key, model


# ── Display helpers ───────────────────────────────────────────────────────────

def _char_width(ch: str) -> int:
    return 2 if unicodedata.east_asian_width(ch) in "WF" else 1


def _width(text: str) -> int:
    return sum(_char_width(ch) for ch in text)


def _fit(text: str, width: int) -> str:
    out, used = [], 0
    for ch in text:
        used += _char_width(ch)
        if used > width - 3:
            return "".join(out) + "..."
        out.append(ch)
    return text


def _clock(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _short(anchor: str) -> str:
    parts = re.split(r" ·\s?", anchor)
    return parts[1] if len(parts) >= 3 else parts[-1]


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _num(value) -> str:
    if value is None:
        return "—"
    return f"{value:.3f}" if isinstance(value, float) else str(value)


def _table(head: list[str], rows: list[list[str]]) -> None:
    widths = [max(_width(r[i]) for r in [head, *rows]) for i in range(len(head))]
    for n, row in enumerate([head, *rows]):
        print("  ".join(c + " " * (w - _width(c)) for c, w in zip(row, widths)).rstrip())
        if n == 0:
            print("  ".join("-" * w for w in widths))


class Live:
    """终端实时进度：每次调用、每个场景各打一行（同时写进日志），底部一行状态每秒刷新。"""

    def __init__(self, title: str, anchors: dict[str, str], log_path: Path, *, prices=None,
                 real_tokens: bool = True) -> None:
        self.title, self.anchors, self.prices, self.real_tokens = title, anchors, prices, real_tokens
        self.log_path = log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log = open(log_path, "a", encoding="utf-8")
        self.tty = sys.stdout.isatty()
        self.flight: dict[int, tuple[str, float]] = {}
        self.seq = 0
        self.reset(len(anchors))

    def reset(self, total: int) -> None:
        self.total, self.done, self.ok, self.failed, self.calls = total, 0, 0, 0, 0
        self.tokens = [0, 0]
        self.per_scene: dict[str, list] = {}
        self.started = time.monotonic()

    def line(self, text: str = "") -> None:
        stamped = f"{datetime.datetime.now():%H:%M:%S} {text}"
        self.log.write(stamped + "\n")
        self.log.flush()
        if self.tty:
            sys.stdout.write("\r\033[K")
        print(stamped, flush=True)
        self.draw()

    def status(self) -> str:
        now = time.monotonic()
        elapsed = now - self.started
        parts = [f"{self.title} {_clock(elapsed)}", f"场景 {self.done}/{self.total}（成功 {self.ok} 失败 {self.failed}）",
                 f"调用 {self.calls}"]
        if 0 < self.done < self.total:
            parts.append(f"预计还要 {_clock(elapsed / self.done * (self.total - self.done))}")
        if self.real_tokens and any(self.tokens):
            text = f"token {self.tokens[0]:,}/{self.tokens[1]:,}"
            if self.prices:
                text += f" 约 {self.tokens[0] / 1e6 * self.prices[0] + self.tokens[1] / 1e6 * self.prices[1]:.3f}"
            parts.append(text)
        if self.flight:
            items = sorted(self.flight.values(), key=lambda x: x[1])
            parts.append("进行中 " + "、".join(f"{name} {now - t:.0f}s" for name, t in items))
        return " | ".join(parts)

    def draw(self) -> None:
        if self.tty:
            sys.stdout.write("\r\033[K" + _fit(self.status(), shutil.get_terminal_size((120, 20)).columns))
            sys.stdout.flush()

    def clear(self) -> None:
        if self.tty:
            sys.stdout.write("\r\033[K")
            sys.stdout.flush()

    def close(self) -> None:
        self.clear()
        self.log.close()

    async def ticker(self) -> None:
        while True:
            await asyncio.sleep(1 if self.tty else 30)
            if self.tty:
                self.draw()
            elif self.flight:
                self.line(self.status())

    def wrap(self, call):
        """包一层模型调用：记下进行中的调用和累计 token。场景名取自 prompt 里的 [场景] 行。"""
        async def wrapped(prompt: str, system_prompt: str = ""):
            head = next((ln[5:] for ln in prompt.splitlines() if ln.startswith("[场景] ")), "?")
            self.seq += 1
            cid, resp = self.seq, None
            self.flight[cid] = (_short(head) + ("（重试）" if RETRY_MARK in prompt else ""), time.monotonic())
            self.draw()
            try:
                resp = await call(prompt, system_prompt)
                return resp
            finally:
                self.flight.pop(cid, None)
                self.calls += 1
                usage = getattr(resp, "usage", None) or {}
                self.tokens[0] += usage.get("prompt_tokens") or 0
                self.tokens[1] += usage.get("completion_tokens") or 0
                self.draw()
        return wrapped

    def on_call(self, key: str, rec: dict) -> None:
        stat = self.per_scene.setdefault(key, [0, 0.0])
        stat[0] += 1
        stat[1] += rec["seconds"]
        p, c = rec.get("prompt_tokens"), rec.get("completion_tokens")
        chunk = f" 块 {rec['chunk']}/{rec['chunks']}" if rec.get("chunks", 1) > 1 else ""
        mark = "✓" if rec["ok"] else f"✗ [{error_kind(rec['errors'])}]"
        text = f"   {mark} {self.anchors.get(key, key)}{chunk} 第 {rec['attempt']} 次 {rec['seconds']:.1f}s"
        if self.real_tokens and (p or c):
            text += f"  token {p or 0:,}/{c or 0:,}"
        if rec.get("quote_fixes"):
            text += f"  修复 {rec['quote_fixes']} 处引号"
        if rec.get("format_fixes"):
            text += f"  规范 {rec['format_fixes']} 处格式"
        if rec.get("dropped"):
            text += f"  丢弃或降级 {len(rec['dropped'])} 条"
        if not rec["ok"]:
            errors = rec["errors"]
            text += f"  {errors[0][:120]}" + (f"（另有 {len(errors) - 1} 条）" if len(errors) > 1 else "")
            if rec.get("response_file"):
                text += f"  → {rec['response_file']}"
        self.line(text)

    def on_scene(self, key: str, status: str) -> None:
        self.done += 1
        if status == "ok":
            self.ok += 1
        else:
            self.failed += 1
        calls, seconds = self.per_scene.get(key, [0, 0.0])
        extra = f"  调用 {calls} 次 {seconds:.1f}s" if calls else ""
        self.line(f"[{self.done}/{self.total}] {status} {self.anchors.get(key, key)}{extra}")


class _LiveLogHandler(logging.Handler):
    """把运行期间的警告打进进度输出，而不是直接写 stderr 把状态行冲乱。"""

    live: Live | None = None

    def emit(self, record: logging.LogRecord) -> None:
        text = f"   [{record.levelname}] {record.name}: {record.getMessage()}"
        if self.live:
            self.live.line(text)
        else:
            print(text, file=sys.stderr)


_LOG = _LiveLogHandler(logging.WARNING)
logging.basicConfig(level=logging.WARNING, handlers=[_LOG])
for _quiet in ("core.utils.llm", "core.canon.builder.extract"):
    logging.getLogger(_quiet).setLevel(logging.CRITICAL)


# ── Runs on disk ──────────────────────────────────────────────────────────────

def _summary(run_dir: Path) -> dict | None:
    path = run_dir / "summary.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _run_dirs() -> list[Path]:
    found = {p.parent for p in CANON_DATA.glob("v*/**/canon.sqlite")
             if set(p.parent.relative_to(CANON_DATA).parts) & set(RUN_MODES)}
    return sorted(found, key=lambda d: d.name)


def _category(run_dir: Path) -> str:
    return "/".join(run_dir.relative_to(CANON_DATA).parts[:-1])


def _version_of(path: Path) -> str:
    """数据放在哪个 v<N>/ 下就属于哪一版；不在 .dev_data/canon/v<N>/ 下时按当前 prompt。"""
    try:
        head = path.resolve().relative_to(CANON_DATA.resolve()).parts[0]
    except (ValueError, IndexError):
        return VERSION
    return head if re.fullmatch(r"v\d+", head) else VERSION


def _find_run(ref: str | None, default: str = "latest", *, allow_pilot: bool = False) -> Path:
    ref = ref or default
    if allow_pilot and ref == "pilot":
        return PILOT
    done = [d for d in _run_dirs() if (d / "summary.json").exists()]
    if ref in ("latest", "latest-api", "latest-replay"):
        mode = ref.partition("-")[2]
        pool = [d for d in done if not mode or _summary(d)["mode"] == mode]
        if not pool:
            raise SystemExit(f"还没有{ {'api': '真实接口的', 'replay': '回放的'}.get(mode, '') }运行")
        return pool[-1]
    for cand in (Path(ref), ROOT / ref):
        if (cand / "summary.json").exists():
            return cand.resolve()
    hits = [d for d in done if d.name == ref] or [d for d in done if ref in d.name]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        raise SystemExit(f"找不到运行 {ref!r}，用 python src/tools/canon_dev.py list 查看")
    raise SystemExit(f"{ref!r} 匹配到多个运行：" + "、".join(d.name for d in hits))


def _load_pack():
    if not (PACK / "manifest.json").exists():
        raise SystemExit(f"找不到 story_pack：{PACK}（在 configs/data/ 里设置 story_pack）")
    return load_pack(PACK)


def _samples() -> list[str]:
    names = [p.stem for p in (PACK / "samples").glob("*.txt")]
    return sorted(names, key=lambda n: (not n.isdigit(), int(n) if n.isdigit() else 0, n))


def _scene_keys(args) -> tuple[list[str], str, str]:
    """Select a sample (20, 100, all), a list file or explicit scene keys; returns keys, origin and sample label."""
    sample = getattr(args, "sample", None)
    if getattr(args, "all", False) or sample == "all":
        if args.scenes:
            raise SystemExit("all 与 --scenes 不能同时使用")
        manifest, _, _, _ = _load_pack()
        return list(manifest["scenes"]), "完整 story_pack", "all"
    extra = list(args.scene or [])
    if extra and not args.scenes and not sample:
        keys = list(dict.fromkeys(extra))
        return keys, "命令行指定", str(len(keys))
    name = args.scenes or sample or SCENES
    for path in (PACK / "samples" / f"{name}.txt", PACK / name, Path(name)):
        if path.is_file():
            break
    else:
        raise SystemExit(f"找不到样本或场景清单 {name}；可用样本：{'、'.join([*_samples(), 'all'])}")
    keys = list(dict.fromkeys(canon_cli.read_key_list(str(path)) + extra))
    origin = f"样本 {path.stem}" if path.parent == PACK / "samples" else path.name
    return keys, origin, path.stem


def _print_estimate(keys: list[str], origin: str, repeats: int = 1) -> None:
    est = estimate(PACK, keys, CHARACTER)
    lo, hi = (n * repeats for n in est["input_tokens_range"])
    times = f" × {repeats} 次" if repeats > 1 else ""
    print(f"  场景 {est['scenes']}（{origin}）{times}：首轮调用 {est['calls'] * repeats} 次，"
          f"输入约 {est['input_chars'] * repeats:,} 字 ≈ {lo:,}–{hi:,} token（每字按 0.7–1.3 token 粗估，输出和重试另计）")
    if PRICES:
        print(f"  输入费用约 {lo / 1e6 * PRICES[0]:.3f}–{hi / 1e6 * PRICES[0]:.3f}（按 CANON_PRICE_IN，输出另计）")
    if est["chunked"]:
        print("  会切块的场景：" + "、".join(est["chunked"]))


def _confirm(question: str) -> bool:
    return input(f"{question}（y/N）：").strip().lower() in ("y", "yes")


def _run_line(run_dir: Path) -> str:
    s = _summary(run_dir)
    p = s.get("probes") or {}
    text = (f"完成 {run_dir.name}：成功 {s['ok']}/{s['scenes']}，首次通过 {s['first_pass']}，"
            f"调用 {s['calls']} 次，用时 {s['wall_seconds']}s")
    if p:
        text += f"，探针 KBF {_num(p.get('kbf'))}（召回 {_num(p.get('weighted_recall'))}，边界 {_num(p.get('boundary_accuracy'))}）"
    return text


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_list(args) -> int:
    runs = _run_dirs()
    if not runs:
        print("还没有运行。可以先试 python src/tools/canon_dev.py estimate 或 run --replay pilot。")
        return 0
    head = ["运行", "类别", "模型", "prompt", "成功", "首过", "KBF", "召回", "边界", "裁判引证", "token 入/出", "费用"]
    rows = []
    for d in runs:
        s = _summary(d)
        if s is None:
            rows.append([d.name, _category(d), "未完成", *[""] * 9])
            continue
        p, j, t = s.get("probes") or {}, s.get("judge") or {}, s.get("tokens") or {}
        tokens = f"{t['prompt']:,}/{t['completion']:,}" if t and s["mode"] == "api" else "—"
        rows.append([d.name, _category(d), s["model"], s["prompt_version"].removeprefix("canon-extract-"),
                     f"{s['ok']}/{s['scenes']}", str(s["first_pass"]), _num(p.get("kbf")),
                     _num(p.get("weighted_recall")), _num(p.get("boundary_accuracy")),
                     _num(j.get("citation_recall")), tokens, _num(s.get("cost"))])
    _table(head, rows)
    print(f"\n数据目录 {_rel(CANON_DATA)}/：v<N>/<样本>/api|replay|repeats/ 运行　v<N>/sources/ 外部模型原始输出　"
          "v<N>/chat/ 试聊库　v<N>/all/build/ 全库构建　compare/ 对比　logs/ 中断的日志")
    print("打开审阅页：python src/tools/canon_dev.py open <运行>")
    return 0


def cmd_estimate(args) -> int:
    _load_pack()
    keys, origin, _ = _scene_keys(args)
    _print_estimate(keys, origin)
    return 0


async def cmd_run(args) -> int:
    _, scenes, characters, _ = _load_pack()
    keys, origin, sample = _scene_keys(args)
    missing = [k for k in keys if k not in scenes]
    if missing:
        raise SystemExit("story_pack 里没有这些场景：" + "、".join(missing))
    find_character(characters, CHARACTER)
    anchors = {k: f"{i:02d} {_short(scenes[k]['anchor'])}" for i, k in enumerate(keys, 1)}
    repeats = max(1, args.repeats)
    concurrency = args.concurrency or CONCURRENCY
    probes = None if args.no_probes or not PROBES.exists() else load_probes(PROBES)
    baseline_ref = BASELINE if args.baseline is None else args.baseline
    baseline_dir = None if baseline_ref in ("", "none") else _find_run(baseline_ref, allow_pilot=True)

    source = model_type = None
    version = VERSION
    if args.replay and args.facts:
        raise SystemExit("--facts 需要真实模型接口，不能与 --replay 同用")
    if args.replay:
        source = _find_run(args.replay, allow_pilot=True)
        version = _version_of(source)
        mode, model, key, api_url = "replay", "replay", "replay", ""
        label = args.label or f"replay-{source.name}"
        print(f"[canon] 回放 {_rel(source)}（回复是当时生成的，不是用当前 prompt）")
    else:
        mode = "api"
        model_type = _model_type(args.model_type, "CANON_MODEL_TYPE", "MODEL_TYPE")
        api_url, key, model = _model_info(model_type)
        label = args.label or f"{model_type}-{model}"
        print(f"[canon] 模型 {model_type} · {model} · {api_url}")
    facts_enabled = mode == "api" and args.facts is not False
    print(f"[canon] prompt {PROMPT_VERSION} · 目标角色 {CHARACTER} · 并发 {concurrency} · 超时 {TIMEOUT:g}s")
    print("[canon] 时间事实候选：" + ("事件基准后自动抽取" if facts_enabled else "本次不抽取"))
    _print_estimate(keys, origin, repeats)
    if probes is not None:
        drafts = sum(1 for p in probes if p.get("status") == "draft")
        print(f"[canon] 探针 {len(probes)} 条" + (f"（{drafts} 条是草稿）" if drafts else "") + f"：{_rel(PROBES)}")
    else:
        print("[canon] 不用探针评分" + ("" if args.no_probes else f"（没找到 {_rel(PROBES)}）"))
    print(f"[canon] 基线 {baseline_dir.name if baseline_dir else '无'}")
    out_root = bench_dir(mode, repeats, CANON_DATA, version=version, sample=sample)
    print(f"[canon] 结果写到 {_rel(out_root)}/")
    if mode == "api" and not args.yes and not _confirm(f"确认开始？会调用 {model_type} 接口，按用量计费的接口会产生费用"):
        print("已取消。")
        return 0

    answers = None
    if mode == "replay":
        answers, skipped = replay_answers(PACK, keys, load_replay(source), CHARACTER)
        if skipped:
            print("[canon] 回放数据里没有、或需要切块而无法回放的场景（会记为失败）：" + "、".join(skipped))
    baseline = _summary(baseline_dir) if baseline_dir else None
    baseline_results = load_results(baseline_dir) if baseline_dir else None
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    group = out_root / f"{stamp}-{slug(label)}-x{repeats}" if repeats > 1 else None
    log_path = LOGS / f"{stamp}-{slug(label)}.log"
    live = Live("回放" if mode == "replay" else "抽取", anchors, log_path,
                prices=PRICES if mode == "api" else None, real_tokens=mode == "api")
    common = dict(character_id=CHARACTER, concurrency=concurrency, timeout=TIMEOUT, prices=PRICES,
                  baseline=baseline, baseline_results=baseline_results,
                  baseline_name=baseline_dir.name if baseline_dir else "", probes=probes,
                  source=_rel(source) if source else "", echo=lambda _: None,
                  on_call=live.on_call, on_scene=live.on_scene)

    fact_reports = []

    async def execute(call, url: str) -> list[Path]:
        ticker = asyncio.create_task(live.ticker())
        _LOG.live = live
        dirs = []
        try:
            for i in range(1, repeats + 1):
                live.reset(len(keys))
                live.line(f"开始{f'第 {i}/{repeats} 次' if repeats > 1 else ''}运行：{len(keys)} 个场景")
                run_dir = await run_bench(PACK, keys, group or out_root, call=live.wrap(call), mode=mode, model=model,
                                          api_url=url, label=f"r{i}" if repeats > 1 else label, **common)
                live.line("事件阶段 " + _run_line(run_dir))
                if facts_enabled:
                    live.line("开始时间事实候选阶段")
                    fact_client = SimpleLLMClient(url, key, model, timeout=TIMEOUT, temperature=0)
                    fact_report = await canon_cli.run_fact_benchmark(
                        run_dir, keys, fact_client.text_chat, model, concurrency=concurrency)
                    fact_reports.append(fact_report)
                    live.line(f"时间事实候选：{fact_report['complete']}/{fact_report['selected']} 场景，"
                              f"失败 {fact_report['failed']}，跳过 {len(fact_report['skipped'])}，"
                              f"模型调用 {fact_report['model_calls']} 次")
                else:
                    write_fact_summary(run_dir, None, reason="回放模式" if mode == "replay" else "显式 --no-facts")
                live.line("运行结束：" + str(run_dir / "report.md"))
                dirs.append(run_dir)
        finally:
            _LOG.live = None
            ticker.cancel()
            live.close()
        return dirs

    try:
        if mode == "replay":
            with ReplayServer(answers) as server:
                client = SimpleLLMClient(server.url, key, model, timeout=TIMEOUT)
                dirs = await execute(client.text_chat, server.url)
        else:
            client = SimpleLLMClient(api_url, key, model, timeout=TIMEOUT)
            dirs = await execute(client.text_chat, api_url)
    except (KeyboardInterrupt, asyncio.CancelledError):
        _INTERRUPTED.append(f"已中断。没跑完的运行在 {_rel(out_root)}/ 下，list 里标为未完成；日志：{_rel(log_path)}")
        raise

    home = group or dirs[0]
    if group:
        stab = stability([load_results(d) for d in dirs])
        (group / "stability.json").write_text(json.dumps(stab, ensure_ascii=False, indent=1), encoding="utf-8")
        (group / "stability.md").write_text("\n".join(canon_cli.render_stability(stab, dirs)), encoding="utf-8")
    shutil.move(log_path, home / "console.log")
    print()
    if group:
        for d in dirs:
            print(_run_line(d))
    print(f"报告：{_rel(dirs[-1] / 'report.md')}")
    print(f"审阅页：{_rel(dirs[-1] / 'review.html')}（python src/tools/canon_dev.py open {dirs[-1].name}）")
    if group:
        print(f"重测信度：{_rel(group / 'stability.md')}")
    return 0 if all(_summary(d)["failed"] == 0 for d in dirs) and all(
        r["failed"] == 0 and not r["skipped"] for r in fact_reports) else 1


async def cmd_build(args) -> int:
    """Incrementally build all events and fact candidates in one database."""
    from core.canon.storage.store import CanonStore
    manifest, _, _, _ = _load_pack()
    model_type = _model_type(args.model_type, "CANON_MODEL_TYPE", "MODEL_TYPE")
    api_url, key, model = _model_info(model_type)
    db_path = Path(args.db) if args.db else CANON_DATA / VERSION / "all" / "build" / "canon.sqlite"
    if not args.yes and not _confirm(
            f"确认全量构建 {len(manifest['scenes'])} 场景到 {_rel(db_path)}？会调用 {model_type} 接口"):
        print("已取消。")
        return 0
    store = CanonStore(db_path)
    await store.open()
    client = SimpleLLMClient(api_url, key, model, timeout=TIMEOUT, temperature=0)
    try:
        report = await Importer(
            store, client.text_chat, model=model, character=CHARACTER,
            concurrency=args.concurrency or CONCURRENCY, timeout=TIMEOUT,
            progress=lambda scene, status: print(f"[event] {status:6} {scene}", flush=True),
        ).run(PACK)
        print("\n".join(report.lines()))
        async with store.db.execute("SELECT scene_key FROM scenes ORDER BY narrative_pos") as cur:
            keys = [row["scene_key"] for row in await cur.fetchall()]
        out = db_path.parent / f"facts-candidates-{datetime.datetime.now():%Y%m%d-%H%M%S}.jsonl"
        fact_report = await canon_cli.run_fact_pipeline(
            store, keys, client.text_chat, model, out, concurrency=args.concurrency or CONCURRENCY)
        await canon_cli.write_fact_review_page(store, keys, fact_report, out,
                                               db_path.parent / "review.html")
    finally:
        await store.close()
    print(f"[canon] 全量数据库 {_rel(db_path)}")
    print(f"[canon] 时间事实候选 {fact_report['candidates']} 条，"
          f"{fact_report['complete']}/{fact_report['selected']} 场景，"
          f"失败 {fact_report['failed']}，跳过 {len(fact_report['skipped'])}，"
          f"审阅组 {fact_report['review_groups']}")
    print(f"[canon] 审阅包 {_rel(out.with_suffix('.review.json'))}")
    print(f"[canon] 审阅页 {_rel(db_path.parent / 'review.html')}")
    return 0 if report.failed == 0 and fact_report["failed"] == 0 and not fact_report["skipped"] else 1


async def cmd_facts(args) -> int:
    """Resume the fact pass on an existing run database."""
    from core.canon.storage.store import CanonStore
    run_dir = _find_run(args.run, "latest-api")
    summary = _summary(run_dir)
    if summary["mode"] != "api":
        raise SystemExit("时间事实候选只支持真实接口运行")
    model_type = _model_type(args.model_type, "CANON_MODEL_TYPE", "MODEL_TYPE")
    api_url, key, model = _model_info(model_type)
    if model != summary["model"]:
        raise SystemExit(f"运行使用 {summary['model']}，当前模型为 {model}；请指定相同模型后续跑")
    out = run_dir / "facts-candidates.jsonl"
    if out.exists():
        out = run_dir / f"facts-candidates-{datetime.datetime.now():%Y%m%d-%H%M%S}.jsonl"
    client = SimpleLLMClient(api_url, key, model, timeout=TIMEOUT, temperature=0)
    store = CanonStore(run_dir / "canon.sqlite")
    await store.open()
    try:
        async with store.db.execute("SELECT scene_key FROM scenes ORDER BY narrative_pos") as cur:
            keys = [row["scene_key"] for row in await cur.fetchall()]
    finally:
        await store.close()
    report = await canon_cli.run_fact_benchmark(run_dir, keys, client.text_chat, model,
                                                 concurrency=args.concurrency or CONCURRENCY, out=out)
    print(f"事实候选 {report['complete']}/{report['selected']}；审阅包 {_rel(out.with_suffix('.review.json'))}")
    return 0 if report["failed"] == 0 and not report["skipped"] else 1


async def cmd_judge(args) -> int:
    run_dir = _find_run(args.run, "latest-api")
    _, scenes, _, _ = _load_pack()
    results = load_results(run_dir)
    anchors = {k: f"{i:02d} {_short(scenes[k]['anchor'])}" for i, k in enumerate(results, 1) if k in scenes}
    model_type = _model_type(args.model_type, "CANON_JUDGE_MODEL_TYPE", "CANON_MODEL_TYPE", "MODEL_TYPE")
    api_url, key, model = _model_info(model_type)
    concurrency = args.concurrency or CONCURRENCY
    print(f"[canon] 裁判 {run_dir.name}：{len(results)} 个成功场景 × {args.repeats} 次 = {len(results) * args.repeats} 次调用")
    print(f"[canon] 裁判模型 {model_type} · {model} · {api_url}（temperature 0）")
    print("[canon] 注意：会把这次运行引用到的剧情原文行发给上面的接口")
    if (run_dir / "judge.jsonl").exists():
        print("[canon] 这个运行已经有裁判结果，会被覆盖")
    if not args.yes and not _confirm("确认开始？"):
        print("已取消。")
        return 0
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = LOGS / f"{stamp}-judge-{slug(run_dir.name)}.log"
    live = Live("裁判", anchors, log_path)
    client = SimpleLLMClient(api_url, key, model, timeout=TIMEOUT, temperature=0)
    ticker = asyncio.create_task(live.ticker())
    _LOG.live = live
    try:
        j, failures = await canon_cli.judge_into(run_dir, PACK, live.wrap(client.text_chat), model=model,
                                                 character_id=CHARACTER, repeats=args.repeats,
                                                 concurrency=concurrency, timeout=TIMEOUT, labels=args.labels,
                                                 progress=live.on_scene)
    except (KeyboardInterrupt, asyncio.CancelledError):
        _INTERRUPTED.append(f"已中断，裁判结果没有写入；日志：{_rel(log_path)}")
        raise
    finally:
        _LOG.live = None
        ticker.cancel()
        live.close()
    shutil.move(log_path, run_dir / "judge.log")
    print(f"\n裁判 {j['events']} 个事件：引证召回率 {_num(j['citation_recall'])}，引证精确率 {_num(j['citation_precision'])}，"
          f"渠道支撑率 {_num(j['channel_support'])}")
    if failures:
        print("裁判失败的场景：" + "、".join(failures))
    print(f"报告已更新：{_rel(run_dir / 'report.md')}")
    return 0 if not failures else 1


async def cmd_compare(args) -> int:
    dirs = [_find_run(r, allow_pilot=True) for r in args.runs]
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = (f"{stamp}-{dirs[0].name}-vs-{dirs[1].name}.md" if len(dirs) == 2
            else f"{stamp}-stability-{len(dirs)}runs.md")
    out = COMPARE / name
    out.parent.mkdir(parents=True, exist_ok=True)
    await canon_cli.cmd_compare(argparse.Namespace(runs=[str(d) for d in dirs], out=str(out)))
    print()
    print(out.read_text(encoding="utf-8"))
    return 0


def cmd_open(args) -> int:
    run_dir = _find_run(args.run)
    target = run_dir / ("report.md" if args.report else "review.html")
    print(_rel(target))
    if shutil.which("wslpath") and shutil.which("explorer.exe"):
        win = subprocess.run(["wslpath", "-w", str(target)], capture_output=True, text=True).stdout.strip()
        subprocess.run(["explorer.exe", win])
    else:
        webbrowser.open(target.as_uri())
    return 0


def _scene_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("sample", nargs="?", metavar="样本",
                   help=f"story_pack/samples/ 里的样本名，如 20、100，或 all 表示全部场景；默认 {SCENES}")
    p.add_argument("--scenes", metavar="清单", help="改用别的场景清单文件（story_pack 里的文件名或路径）")
    p.add_argument("--scene", action="append", metavar="scene_key", help="追加单个场景，可重复；只给它时只跑这些场景")
    p.add_argument("--all", action="store_true", help="同样本 all：使用 story_pack 的全部场景")


def main() -> int:
    if sys.argv[1:2] == ["retrieval"]:
        from core_eval.canon.retrieval import main as retrieval_main
        return retrieval_main(sys.argv[2:])
    if sys.argv[1:2] == ["test"]:
        from tools.canon_chat import main as chat_main
        return chat_main(sys.argv[2:])
    ap = argparse.ArgumentParser(prog="python src/tools/canon_dev.py",
                                 description="canon 抽取基准的开发工具（模型取自 configs/）")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list", help="列出已有的运行")
    sub.add_parser("retrieval", help="共享 embedding/rerank 的向量构建与检索实验")
    sub.add_parser("test", help="只读 canon 库试聊，聊天只保存在内存")
    _scene_args(sub.add_parser("estimate", help="估算调用次数和输入量，不调用接口"))
    p = sub.add_parser("run", help="跑一次基准")
    _scene_args(p)
    p.add_argument("--replay", metavar="来源", help="回放 pilot（v1 的 Luna 试跑）或某个运行，不调用真实接口；结果放在来源所属的版本下")
    p.add_argument("--repeats", type=int, default=1, help="同一配置跑几次并报告重测信度（费用随之翻倍）")
    p.add_argument("--label", help="运行目录名里的标签，默认是模型类型加模型名")
    p.add_argument("--baseline", metavar="运行", help="对比的基线，none 表示不对比；默认 CANON_BASELINE")
    p.add_argument("--no-probes", action="store_true", help="不用金标准探针评分")
    p.add_argument("--model-type", choices=MODEL_TYPES, help="覆盖 CANON_MODEL_TYPE / MODEL_TYPE")
    p.add_argument("--concurrency", type=int, help=f"并发数，默认 {CONCURRENCY}")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--facts", dest="facts", action="store_true", default=None,
                       help="事件基准结束后抽取时间事实候选（真实接口默认开启）")
    group.add_argument("--no-facts", dest="facts", action="store_false",
                       help="仅跑 V7 事件基准，不抽取时间事实候选")
    p.add_argument("-y", "--yes", action="store_true", help="跳过开始前的确认")
    p = sub.add_parser("build", help="增量构建全库事件及时间事实候选，中断后重跑同一命令")
    p.add_argument("--db", help="全量数据库；默认 .dev_data/canon/<当前 prompt 版本>/all/build/canon.sqlite")
    p.add_argument("--model-type", choices=MODEL_TYPES)
    p.add_argument("--concurrency", type=int)
    p.add_argument("-y", "--yes", action="store_true")
    p = sub.add_parser("facts", help="对已有真实运行续跑时间事实候选")
    p.add_argument("run", nargs="?", help="运行，默认 latest-api")
    p.add_argument("--model-type", choices=MODEL_TYPES)
    p.add_argument("--concurrency", type=int)
    p = sub.add_parser("judge", help="LLM 裁判（会把引用的原文行发给裁判接口）")
    p.add_argument("run", nargs="?", help="运行，默认 latest-api")
    p.add_argument("--repeats", type=int, default=1, help="每个场景判几次，≥2 时报告重测一致性（建议 3）")
    p.add_argument("--labels", help="人工标注（JSONL：scene、event、support、channel_ok）")
    p.add_argument("--model-type", choices=MODEL_TYPES, help="覆盖 CANON_JUDGE_MODEL_TYPE")
    p.add_argument("--concurrency", type=int, help=f"并发数，默认 {CONCURRENCY}")
    p.add_argument("-y", "--yes", action="store_true", help="跳过开始前的确认")
    p = sub.add_parser("compare", help="两个运行逐事件对比；三个以上报告重测信度")
    p.add_argument("runs", nargs="+", metavar="运行")
    p = sub.add_parser("open", help="用浏览器打开审阅页")
    p.add_argument("run", nargs="?", help="运行，默认 latest")
    p.add_argument("--report", action="store_true", help="打开 report.md 而不是 review.html")
    args = ap.parse_args()
    if args.cmd == "compare" and len(args.runs) < 2:
        ap.error("compare 至少需要两个运行")
    handler = {"list": cmd_list, "estimate": cmd_estimate, "run": cmd_run, "build": cmd_build, "facts": cmd_facts, "judge": cmd_judge,
               "compare": cmd_compare, "open": cmd_open}[args.cmd or "list"]
    try:
        result = handler(args)
        return asyncio.run(result) if asyncio.iscoroutine(result) else result
    except KeyboardInterrupt:
        print("\n" + (_INTERRUPTED[-1] if _INTERRUPTED else "已中断。"))
        return 130


if __name__ == "__main__":
    sys.exit(main())
