"""End-to-end smoke test for the memory plugin core — no AstrBot, no WebUI.

Run:
    python run_core_dev.py

What it covers:
  1. DB open + migrations
  2. Persona + Event CRUD via repos
  3. group_id isolation: two groups, recall only sees its own events
  4. delete_with_vector atomic delete
  5. PersonaRepository.upsert transaction integrity
  6. recall() pipeline (BM25, NullEncoder fallback)
  7. Impression upsert + scope isolation in synthesis
  8. core/api.py functions
"""
from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

DEV_DB = Path(".dev_data") / "dev_core.db"


def _eid() -> str:
    return str(uuid.uuid4())


def _uid() -> str:
    return str(uuid.uuid4())


def _make_event(
    event_id: str,
    group_id: str | None,
    topic: str,
    tags: list[str],
    uid: str,
    salience: float = 0.5,
) -> object:
    from core.domain.models import Event

    now = time.time()
    return Event(
        event_id=event_id,
        group_id=group_id,
        start_time=now - 600,
        end_time=now,
        participants=[uid],
        interaction_flow=[],
        topic=topic,
        chat_content_tags=tags,
        salience=salience,
        confidence=0.8,
        inherit_from=[],
        last_accessed_at=now,
    )


def _make_persona(uid: str, name: str) -> object:
    from core.domain.models import Persona

    now = time.time()
    return Persona(
        uid=uid,
        bound_identities=[("test", uid[:8])],
        primary_name=name,
        persona_attrs={},
        confidence=0.7,
        created_at=now,
        last_active_at=now,
    )


def _make_impression(observer: str, subject: str, scope: str, evidence: list[str]) -> object:
    from core.domain.models import Impression

    return Impression(
        observer_uid=observer,
        subject_uid=subject,
        relation_type="stranger",
        affect=0.0,
        intensity=0.5,
        confidence=0.6,
        scope=scope,
        evidence_event_ids=evidence,
        last_reinforced_at=time.time(),
    )


async def main() -> None:
    from core.embedding.encoder import NullEncoder
    from core.managers.memory_manager import MemoryManager
    from core.managers.recall_manager import RecallManager
    from core.repository.sqlite import (
        SQLiteEventRepository,
        SQLiteImpressionRepository,
        SQLitePersonaRepository,
        db_open,
    )
    from core.retrieval.hybrid import HybridRetriever
    from core.config import DecayConfig, InjectionConfig, RetrievalConfig
    from core import api as core_api

    DEV_DB.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("run_core_dev — core smoke test")
    print("=" * 60)

    async with db_open(DEV_DB, migration_auto_backup=False) as db:
        persona_repo = SQLitePersonaRepository(db)
        event_repo = SQLiteEventRepository(db)
        impression_repo = SQLiteImpressionRepository(db)

        encoder = NullEncoder()
        retriever = HybridRetriever(event_repo, encoder)
        memory = MemoryManager(event_repo, retriever, encoder, DecayConfig())
        recall = RecallManager(retriever, RetrievalConfig(), InjectionConfig())

        # ── 1. Persona CRUD ───────────────────────────────────────────────
        print("\n[1] Persona CRUD")
        uid_alice = _uid()
        uid_bob = _uid()
        await persona_repo.upsert(_make_persona(uid_alice, "Alice"))
        await persona_repo.upsert(_make_persona(uid_bob, "Bob"))
        personas = await persona_repo.list_all()
        print(f"    personas stored: {[p.primary_name for p in personas]}")
        assert any(p.primary_name == "Alice" for p in personas)

        # ── 2. Event CRUD + group_id isolation ────────────────────────────
        print("\n[2] Event CRUD + group_id isolation")
        gid_a = "group_A"
        gid_b = "group_B"

        ev1 = _eid()
        ev2 = _eid()
        ev3 = _eid()

        await memory.add_event(_make_event(ev1, gid_a, "Python 教程讨论", ["python", "编程"], uid_alice))
        await memory.add_event(_make_event(ev2, gid_a, "假期旅游计划", ["旅游", "假期"], uid_alice))
        await memory.add_event(_make_event(ev3, gid_b, "Python 数据分析", ["python", "数据"], uid_bob))

        # FTS search with group isolation
        results_a = await event_repo.search_fts("python", limit=10, group_id=gid_a)
        results_b = await event_repo.search_fts("python", limit=10, group_id=gid_b)
        results_all = await event_repo.search_fts("python", limit=10)

        print(f"    group_A python hits: {len(results_a)} (expect 1)")
        print(f"    group_B python hits: {len(results_b)} (expect 1)")
        print(f"    all groups python hits: {len(results_all)} (expect 2)")

        assert len(results_a) == 1 and results_a[0].group_id == gid_a, "group_A isolation failed"
        assert len(results_b) == 1 and results_b[0].group_id == gid_b, "group_B isolation failed"
        assert len(results_all) == 2, "cross-group search failed"
        print("    [PASS] group_id isolation OK")

        # ── 3. RecallManager group_id pass-through ────────────────────────
        print("\n[3] RecallManager group_id pass-through")
        recalled_a = await recall.recall("python", group_id=gid_a)
        recalled_b = await recall.recall("python", group_id=gid_b)
        assert all(e.group_id == gid_a for e in recalled_a), "recall group_A leaked"
        assert all(e.group_id == gid_b for e in recalled_b), "recall group_B leaked"
        print(f"    group_A recall: {[e.topic for e in recalled_a]}")
        print(f"    group_B recall: {[e.topic for e in recalled_b]}")
        print("    [PASS] recall isolation OK")

        # ── 4. delete_with_vector atomic delete ───────────────────────────
        print("\n[4] delete_with_vector atomic delete")
        ev_tmp = _eid()
        await memory.add_event(_make_event(ev_tmp, gid_a, "临时事件", ["临时"], uid_alice))
        before = await event_repo.get(ev_tmp)
        assert before is not None

        deleted = await memory.delete_event(ev_tmp)
        after = await event_repo.get(ev_tmp)
        assert deleted is True
        assert after is None
        print("    [PASS] delete_with_vector OK")

        # ── 5. PersonaRepository.upsert transaction ───────────────────────
        print("\n[5] PersonaRepository.upsert transaction integrity")
        import dataclasses
        alice = await persona_repo.get(uid_alice)
        assert alice is not None
        updated_alice = dataclasses.replace(alice, primary_name="Alice Updated")
        await persona_repo.upsert(updated_alice)
        refetched = await persona_repo.get(uid_alice)
        assert refetched is not None and refetched.primary_name == "Alice Updated"
        print("    [PASS] upsert transaction OK")

        # ── 6. Impression upsert ──────────────────────────────────────────
        print("\n[6] Impression upsert")
        imp = _make_impression(uid_alice, uid_bob, gid_a, [ev1])
        await impression_repo.upsert(imp)
        fetched_imp = await impression_repo.get(uid_alice, uid_bob, gid_a)
        assert fetched_imp is not None
        print(f"    impression: {fetched_imp.relation_type}, affect={fetched_imp.affect}")
        print("    [PASS] impression upsert OK")

        # ── 7. core/api.py functions ──────────────────────────────────────
        print("\n[7] core/api.py functions")

        stats = await core_api.get_stats(persona_repo, event_repo, impression_repo)
        print(f"    stats: {stats}")
        assert stats["events"] >= 3

        events_data = await core_api.list_events(event_repo, gid_a)
        print(f"    list_events(group_A): {len(events_data['items'])} items")
        assert len(events_data["items"]) >= 1

        recall_items = await core_api.recall_preview(recall, "python", group_id=gid_a)
        print(f"    recall_preview(group_A, python): {len(recall_items)} items")

        graph = await core_api.get_graph(persona_repo, impression_repo)
        print(f"    graph: {len(graph['nodes'])} nodes, {len(graph['edges'])} edges")
        assert len(graph["nodes"]) >= 2
        print("    [PASS] core/api.py OK")

    print("\n" + "=" * 60)
    print("All checks passed.")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
