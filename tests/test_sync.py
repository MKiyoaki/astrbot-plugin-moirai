"""Tests for Phase 10: Markdown reverse sync (FileWatcher + parser + ReverseSyncer)."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.repository.memory import (
    InMemoryImpressionRepository,
    InMemoryPersonaRepository,
)
from core.sync.parser import parse_impressions_md
from core.sync.syncer import ReverseSyncer, _USER_EDIT_CONFIDENCE_FLOOR
from core.sync.watcher import FileWatcher


# ---------------------------------------------------------------------------
# Sample IMPRESSIONS.md content matching persona_impressions.md.j2 output
# ---------------------------------------------------------------------------

_SAMPLE_MD = """\
# Alice 的印象记录

> 本文件可由用户手动编辑，修改将在下次同步时写回数据库（Phase 10）。

---

## 来自 `observer-uid-001` 的印象（范围：global）

| 字段 | 值 |
|------|----|
| 关系类型 | friend |
| 情感倾向 | 正面（+0.70） |
| 强度 | 80% |
| 置信度 | 75% |
| 最近强化 | 2024-01-01 00:00 UTC |

**依据事件：** ev001, ev002

---

## 来自 `observer-uid-002` 的印象（范围：g1）

| 字段 | 值 |
|------|----|
| 关系类型 | colleague |
| 情感倾向 | 中性（+0.10） |
| 强度 | 40% |
| 置信度 | 60% |
| 最近强化 | 2024-01-02 00:00 UTC |

"""

_EMPTY_MD = """\
# Bob 的印象记录

> 本文件可由用户手动编辑，修改将在下次同步时写回数据库（Phase 10）。

暂无印象记录
"""


# ---------------------------------------------------------------------------
# parser tests
# ---------------------------------------------------------------------------

def test_parse_returns_correct_count() -> None:
    imps = parse_impressions_md(_SAMPLE_MD, "subject-uid-001")
    assert len(imps) == 2


def test_parse_first_impression_fields() -> None:
    imps = parse_impressions_md(_SAMPLE_MD, "subject-uid-001")
    imp = imps[0]
    assert imp.observer_uid == "observer-uid-001"
    assert imp.subject_uid == "subject-uid-001"
    assert imp.relation_type == "friend"
    assert imp.affect == pytest.approx(0.70, abs=0.001)
    assert imp.intensity == pytest.approx(0.80, abs=0.001)
    assert imp.confidence == pytest.approx(0.75, abs=0.001)
    assert imp.scope == "global"
    assert "ev001" in imp.evidence_event_ids
    assert "ev002" in imp.evidence_event_ids


def test_parse_second_impression_fields() -> None:
    imps = parse_impressions_md(_SAMPLE_MD, "subject-uid-001")
    imp = imps[1]
    assert imp.observer_uid == "observer-uid-002"
    assert imp.scope == "g1"
    assert imp.relation_type == "colleague"
    assert imp.affect == pytest.approx(0.10, abs=0.001)
    assert imp.intensity == pytest.approx(0.40, abs=0.001)


def test_parse_empty_impressions_section() -> None:
    imps = parse_impressions_md(_EMPTY_MD, "subject-uid-001")
    assert imps == []


def test_parse_no_evidence_events() -> None:
    md = _SAMPLE_MD.replace("**依据事件：** ev001, ev002\n", "")
    imps = parse_impressions_md(md, "s1")
    assert imps[0].evidence_event_ids == []


def test_parse_negative_affect() -> None:
    md = _SAMPLE_MD.replace("正面（+0.70）", "负面（-0.80）")
    imps = parse_impressions_md(md, "s1")
    assert imps[0].affect == pytest.approx(-0.80, abs=0.001)


def test_parse_neutral_affect() -> None:
    md = _SAMPLE_MD.replace("正面（+0.70）", "中性（+0.05）")
    imps = parse_impressions_md(md, "s1")
    assert imps[0].affect == pytest.approx(0.05, abs=0.001)


def test_parse_clamps_intensity_over_100() -> None:
    md = _SAMPLE_MD.replace("| 强度 | 80% |", "| 强度 | 150% |")
    imps = parse_impressions_md(md, "s1")
    assert imps[0].intensity == pytest.approx(1.0, abs=0.001)


def test_parse_clamps_confidence_over_100() -> None:
    md = _SAMPLE_MD.replace("| 置信度 | 75% |", "| 置信度 | 200% |")
    imps = parse_impressions_md(md, "s1")
    assert imps[0].confidence == pytest.approx(1.0, abs=0.001)


def test_parse_incomplete_block_skipped() -> None:
    # Remove the affect row — that block should be skipped
    md = _SAMPLE_MD.replace("| 情感倾向 | 正面（+0.70） |\n", "")
    imps = parse_impressions_md(md, "s1")
    assert len(imps) == 1
    assert imps[0].observer_uid == "observer-uid-002"


def test_parse_full_uid_preserved() -> None:
    # Observer uid must NOT be truncated (the template no longer slices)
    imps = parse_impressions_md(_SAMPLE_MD, "s1")
    assert imps[0].observer_uid == "observer-uid-001"
    assert imps[1].observer_uid == "observer-uid-002"


def test_parse_last_reinforced_at_is_recent() -> None:
    before = time.time()
    imps = parse_impressions_md(_SAMPLE_MD, "s1")
    after = time.time()
    assert before <= imps[0].last_reinforced_at <= after


# ---------------------------------------------------------------------------
# FileWatcher tests
# ---------------------------------------------------------------------------

async def test_watcher_detects_change(tmp_path: Path) -> None:
    target = tmp_path / "test.md"
    target.write_text("v1", encoding="utf-8")

    called: list[Path] = []

    async def cb(p: Path) -> None:
        called.append(p)

    watcher = FileWatcher(poll_interval=1.0)
    watcher.register(target, cb)

    # Ensure mtime changes by sleeping a tiny amount then rewriting
    time.sleep(0.05)
    target.write_text("v2", encoding="utf-8")

    changed = await watcher._check_once()
    assert target in changed
    assert len(called) == 1


async def test_watcher_no_change(tmp_path: Path) -> None:
    target = tmp_path / "test.md"
    target.write_text("v1", encoding="utf-8")

    called: list[Path] = []

    async def cb(p: Path) -> None:
        called.append(p)

    watcher = FileWatcher()
    watcher.register(target, cb)

    changed = await watcher._check_once()
    assert changed == []
    assert called == []


async def test_watcher_missing_file_ignored(tmp_path: Path) -> None:
    target = tmp_path / "missing.md"

    async def cb(p: Path) -> None:
        raise AssertionError("should not be called")

    watcher = FileWatcher()
    watcher.register(target, cb)

    changed = await watcher._check_once()
    assert changed == []


async def test_watcher_unregister_stops_detection(tmp_path: Path) -> None:
    target = tmp_path / "test.md"
    target.write_text("v1", encoding="utf-8")

    called: list[Path] = []

    async def cb(p: Path) -> None:
        called.append(p)

    watcher = FileWatcher()
    watcher.register(target, cb)
    watcher.unregister(target)

    time.sleep(0.05)
    target.write_text("v2", encoding="utf-8")

    changed = await watcher._check_once()
    assert changed == []
    assert called == []


async def test_watcher_callback_error_does_not_propagate(tmp_path: Path) -> None:
    target = tmp_path / "test.md"
    target.write_text("v1", encoding="utf-8")

    async def bad_cb(p: Path) -> None:
        raise RuntimeError("intentional error")

    watcher = FileWatcher()
    watcher.register(target, bad_cb)

    time.sleep(0.05)
    target.write_text("v2", encoding="utf-8")

    # Should not raise despite callback failure
    changed = await watcher._check_once()
    assert target in changed


# ---------------------------------------------------------------------------
# ReverseSyncer tests
# ---------------------------------------------------------------------------

async def test_syncer_on_change_upserts_impressions(tmp_path: Path) -> None:
    uid = "subject-uid-001"
    imp_dir = tmp_path / "personas" / uid
    imp_dir.mkdir(parents=True)
    imp_file = imp_dir / "IMPRESSIONS.md"
    imp_file.write_text(_SAMPLE_MD, encoding="utf-8")

    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    watcher = FileWatcher()
    syncer = ReverseSyncer(tmp_path, pr, ir, watcher)

    await syncer._on_change(imp_file, uid)

    imps1 = await ir.list_by_observer("observer-uid-001")
    assert len(imps1) == 1
    assert imps1[0].subject_uid == uid

    imps2 = await ir.list_by_observer("observer-uid-002")
    assert len(imps2) == 1


async def test_syncer_applies_confidence_floor(tmp_path: Path) -> None:
    uid = "subject-uid-001"
    imp_dir = tmp_path / "personas" / uid
    imp_dir.mkdir(parents=True)
    imp_file = imp_dir / "IMPRESSIONS.md"
    # _SAMPLE_MD has confidence 75% and 60% — both below the 90% floor
    imp_file.write_text(_SAMPLE_MD, encoding="utf-8")

    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    watcher = FileWatcher()
    syncer = ReverseSyncer(tmp_path, pr, ir, watcher)

    await syncer._on_change(imp_file, uid)

    imps = await ir.list_by_observer("observer-uid-001")
    assert imps[0].confidence == pytest.approx(_USER_EDIT_CONFIDENCE_FLOOR, abs=0.001)


async def test_syncer_high_confidence_not_lowered(tmp_path: Path) -> None:
    uid = "s1"
    imp_dir = tmp_path / "personas" / uid
    imp_dir.mkdir(parents=True)
    imp_file = imp_dir / "IMPRESSIONS.md"
    # Set confidence to 95% — above the floor; should stay at 0.95
    md = _SAMPLE_MD.replace("| 置信度 | 75% |", "| 置信度 | 95% |")
    imp_file.write_text(md, encoding="utf-8")

    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    watcher = FileWatcher()
    syncer = ReverseSyncer(tmp_path, pr, ir, watcher)

    await syncer._on_change(imp_file, uid)

    imps = await ir.list_by_observer("observer-uid-001")
    assert imps[0].confidence == pytest.approx(0.95, abs=0.001)


async def test_syncer_register_all_finds_files(tmp_path: Path) -> None:
    for uid in ("uid-a", "uid-b"):
        d = tmp_path / "personas" / uid
        d.mkdir(parents=True)
        (d / "IMPRESSIONS.md").write_text(_SAMPLE_MD, encoding="utf-8")

    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    watcher = FileWatcher()
    syncer = ReverseSyncer(tmp_path, pr, ir, watcher)

    count = await syncer.register_all()
    assert count == 2
    assert len(watcher._watched) == 2


async def test_syncer_register_all_empty_dir(tmp_path: Path) -> None:
    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    watcher = FileWatcher()
    syncer = ReverseSyncer(tmp_path, pr, ir, watcher)

    count = await syncer.register_all()
    assert count == 0


async def test_syncer_register_all_no_personas_dir(tmp_path: Path) -> None:
    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    watcher = FileWatcher()
    syncer = ReverseSyncer(tmp_path, pr, ir, watcher)

    count = await syncer.register_all()
    assert count == 0


async def test_syncer_on_change_missing_file_is_noop(tmp_path: Path) -> None:
    uid = "subject-uid-001"
    missing = tmp_path / "personas" / uid / "IMPRESSIONS.md"

    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    watcher = FileWatcher()
    syncer = ReverseSyncer(tmp_path, pr, ir, watcher)

    await syncer._on_change(missing, uid)
    imps = await ir.list_by_observer("observer-uid-001")
    assert imps == []


async def test_syncer_register_persona_registers_file(tmp_path: Path) -> None:
    uid = "uid-x"
    d = tmp_path / "personas" / uid
    d.mkdir(parents=True)
    (d / "IMPRESSIONS.md").write_text(_SAMPLE_MD, encoding="utf-8")

    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    watcher = FileWatcher()
    syncer = ReverseSyncer(tmp_path, pr, ir, watcher)

    syncer.register_persona(uid)
    assert len(watcher._watched) == 1


async def test_syncer_integration_watcher_triggers_upsert(tmp_path: Path) -> None:
    """End-to-end: file change detected by watcher → syncer writes to DB."""
    uid = "uid-z"
    d = tmp_path / "personas" / uid
    d.mkdir(parents=True)
    imp_file = d / "IMPRESSIONS.md"
    imp_file.write_text(_SAMPLE_MD, encoding="utf-8")

    ir = InMemoryImpressionRepository()
    pr = InMemoryPersonaRepository()
    watcher = FileWatcher()
    syncer = ReverseSyncer(tmp_path, pr, ir, watcher)
    syncer.register_persona(uid)

    # Simulate user edit
    time.sleep(0.05)
    new_md = _SAMPLE_MD.replace("| 关系类型 | friend |", "| 关系类型 | rival |")
    imp_file.write_text(new_md, encoding="utf-8")

    await watcher._check_once()

    imps = await ir.list_by_observer("observer-uid-001")
    assert len(imps) == 1
    assert imps[0].relation_type == "rival"
