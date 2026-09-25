"""canon 导入：读取 story_pack，按 scene_hash 找出要处理的场景，抽取（优先用缓存）并落库，最后编码向量。

一个场景算"已完成"，要同时满足：库里的 scene_hash 等于包里的，且有当前 PROMPT_VERSION 下的成功抽取。
所以 hash 变化、prompt 版本变化、上次失败、上次中途中断的场景都会被重新处理；
命中缓存的场景不调用 API。
"""
from __future__ import annotations

import asyncio
import collections
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .extract import Call, ExtractionOutcome, extract_scene
from .prompt import PROMPT_VERSION
from .store import CanonStore, now_iso

logger = logging.getLogger(__name__)

PACK_FORMAT = 1
ARCHIVE_PACK_FORMAT = 1
VECTOR_BATCH = 64


@dataclass
class ImportReport:
    total_in_pack: int = 0
    selected: int = 0
    up_to_date: int = 0
    added: int = 0
    updated: int = 0
    deleted: int = 0
    cached: int = 0
    extracted: int = 0
    failed: int = 0
    events: int = 0
    vectors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    attempts: int = 0
    quality: collections.Counter = field(default_factory=collections.Counter)
    failures: list[tuple[str, str]] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [
            f"包内场景 {self.total_in_pack}，本次范围 {self.selected}，已是最新 {self.up_to_date}",
            f"新增 {self.added}，更新 {self.updated}，删除 {self.deleted}",
            f"命中缓存 {self.cached}，调用抽取 {self.extracted}（共 {self.attempts} 次调用），失败 {self.failed}",
            f"写入事件 {self.events}，编码向量 {self.vectors}",
            f"token：输入 {self.prompt_tokens}，输出 {self.completion_tokens}",
        ]
        if self.quality:
            out.append("质量指标：" + "；".join(f"{k} ×{v}" for k, v in sorted(self.quality.items())))
        out.extend(f"失败 {key}：{err}" for key, err in self.failures)
        return out


def load_pack(pack_dir: Path | str) -> tuple[dict, dict[str, dict], list[dict], list[dict]]:
    pack = Path(pack_dir)
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("pack_format") != PACK_FORMAT:
        raise ValueError(f"不支持的 story_pack 格式：{manifest.get('pack_format')!r}，需要 {PACK_FORMAT}")
    scenes = {}
    with open(pack / "scenes.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                scene = json.loads(line)
                scenes[scene["scene_key"]] = scene
    characters = json.loads((pack / "characters.json").read_text(encoding="utf-8"))
    seeds = json.loads((pack / "entities_seed.json").read_text(encoding="utf-8"))
    return manifest, scenes, characters, seeds


def load_archive_pack(pack_dir: Path | str) -> tuple[dict, list[dict]]:
    pack = Path(pack_dir)
    manifest = json.loads((pack / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("pack_format") != ARCHIVE_PACK_FORMAT:
        raise ValueError(f"不支持的 archive_pack 格式：{manifest.get('pack_format')!r}，需要 {ARCHIVE_PACK_FORMAT}")
    with open(pack / "archives.jsonl", encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    if {r["archive_id"] for r in records} != set(manifest["archives"]):
        raise ValueError("archive_pack 不完整：manifest 与 archives.jsonl 的档案不一致")
    return manifest, records


async def import_archives(store: CanonStore, archive_pack: Path | str, *,
                          story_pack: Path | str | None = None) -> dict[str, int]:
    """档案是结构化原文，不调用模型；按 archive_hash 增量替换，可选按 story_pack 的实体种子刷新档案链接。"""
    manifest, records = load_archive_pack(archive_pack)
    counts = await store.replace_archives(records, manifest["archives"])
    if story_pack is not None:
        seeds = json.loads((Path(story_pack) / "entities_seed.json").read_text(encoding="utf-8"))
        counts.update({f"seed_{k}": v for k, v in (await store.seed_entities(seeds)).items()})
    await store.set_meta(archive_data_version=str(manifest.get("data_version", "")))
    return counts


def encoder_identity(encoder) -> tuple[int, str]:
    """返回 (维度, encoder_id)。encoder 不可用或维度为 0 时返回 (0, "")。

    共享 provider 用它自己的模型身份（地址、模型、维度），和普通记忆的向量库记法一致。
    """
    if encoder is None:
        return 0, ""
    dim = getattr(encoder, "dim", 0)
    dim = dim() if callable(dim) else dim
    if not dim:
        return 0, ""
    identity = getattr(encoder, "identity", None)
    if isinstance(identity, dict):
        return int(dim), json.dumps({**identity, "dimension": int(dim)}, ensure_ascii=False, sort_keys=True)
    inner = getattr(encoder, "_encoder", encoder)
    name = getattr(inner, "_model_name", "") or getattr(inner, "model_name", "")
    return int(dim), f"{type(inner).__name__}:{name}:{int(dim)}"


class Importer:
    def __init__(self, store: CanonStore, call: Call | None, *, model: str, character: str = "amiya",
                 concurrency: int = 2, timeout: float = 300, encoder=None,
                 progress: Callable[[str, str], None] | None = None,
                 observer: Callable[[str, dict], None] | None = None) -> None:
        self._store, self._call, self._model = store, call, model
        self._character_id = character
        self._sem = asyncio.Semaphore(max(1, concurrency))
        self._timeout, self._encoder = timeout, encoder
        self._progress = progress or (lambda key, status: None)
        self._observer = observer

    async def run(self, pack_dir: Path | str, *, only: set[str] | None = None) -> ImportReport:
        manifest, scenes, characters, seeds = load_pack(pack_dir)
        character = next((c for c in characters if c["character"] == self._character_id), None)
        if character is None:
            raise ValueError(f"story_pack 里没有目标角色 {self._character_id}")
        report = ImportReport(total_in_pack=len(manifest["scenes"]))
        store = self._store
        await store.seed_entities(seeds)

        db_hashes = await store.scene_hashes()
        done = await store.ok_extraction_keys(PROMPT_VERSION)
        for key in sorted(set(db_hashes) - set(manifest["scenes"])):
            await store.delete_scene(key)
            report.deleted += 1
        if only is not None:
            missing = sorted(only - set(manifest["scenes"]))
            if missing:
                raise ValueError(f"这些场景不在 story_pack 里：{missing[:5]}")
        selected = [k for k in manifest["scenes"] if only is None or k in only]
        report.selected = len(selected)
        todo = []
        for key in selected:
            h = manifest["scenes"][key]
            if scenes[key]["scene_hash"] != h:
                raise ValueError(f"{key} 的 scene_hash 与 manifest 不一致，story_pack 不完整")
            if db_hashes.get(key) == h and (key, h) in done:
                report.up_to_date += 1
            else:
                todo.append(key)

        async def process(key: str) -> None:
            scene = scenes[key]
            prev = scenes.get(scene.get("prev_scene_key") or "")
            cached = await store.cached_extraction(key, scene["scene_hash"], PROMPT_VERSION)
            if cached is not None:
                outcome = ExtractionOutcome("ok", result=cached)
                report.cached += 1
            else:
                if self._call is None:
                    raise RuntimeError(f"{key} 需要抽取，但没有配置模型")
                async with self._sem:
                    observe = (lambda rec, key=key: self._observer(key, rec)) if self._observer else None
                    outcome = await extract_scene(self._call, scene, character, prev, timeout=self._timeout,
                                                  observer=observe)
                report.extracted += 1
                report.attempts += outcome.attempts
                report.prompt_tokens += outcome.prompt_tokens or 0
                report.completion_tokens += outcome.completion_tokens or 0
                report.quality.update(outcome.quality)
                await store.put_extraction(key, scene["scene_hash"], PROMPT_VERSION, self._model, outcome)
            written = await store.apply_scene(scene, outcome.result, character)
            report.events += written
            if key in db_hashes:
                report.updated += 1
            else:
                report.added += 1
            if outcome.status != "ok":
                report.failed += 1
                report.failures.append((key, outcome.error or ""))
            self._progress(key, "缓存" if cached is not None else outcome.status)

        results = await asyncio.gather(*(process(k) for k in todo), return_exceptions=True)
        for key, res in zip(todo, results):
            if isinstance(res, Exception):
                report.failed += 1
                report.failures.append((key, f"{type(res).__name__}: {res}"))
                logger.error("[canon] import of %s failed: %s", key, res)

        report.vectors = await self._encode_vectors()
        await store.set_meta(pack_data_version=manifest.get("data_version", ""),
                             upstream_commit=manifest.get("upstream_commit", ""),
                             prompt_version=PROMPT_VERSION, imported_at=now_iso())
        return report

    async def _encode_vectors(self) -> int:
        if self._encoder is None or not self._store.vec_enabled:
            return 0
        pending = await self._store.events_without_vectors()
        written = 0
        for i in range(0, len(pending), VECTOR_BATCH):
            batch = pending[i:i + VECTOR_BATCH]
            vectors = await self._encoder.encode_batch([text for _, text in batch])
            items = [(eid, vec) for (eid, _), vec in zip(batch, vectors) if vec]
            await self._store.put_vectors(items)
            written += len(items)
        return written
