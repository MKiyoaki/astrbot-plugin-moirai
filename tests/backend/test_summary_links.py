from pathlib import Path

import pytest

from core.domain.models import Event
from core.repository.memory import InMemoryEventRepository
from core.tasks.summary_links import (
    refresh_summary_event_links,
    refresh_summary_files_for_event,
)


@pytest.mark.asyncio
async def test_refresh_summary_event_links_updates_stale_title() -> None:
    repo = InMemoryEventRepository()
    await repo.upsert(Event(event_id="abcdef123456", topic="新标题"))
    content = (
        "# g1 Activity Summary\n\n"
        "[主要话题]\n旧摘要\n\n"
        "[事件列表]\n[旧标题] - [abcdef12] | *After Alice sent \"hi\", the topic shifted to | "
        "[未变化] - [deadbeef]\n\n"
        "[情感动态]\n平稳\n"
    )

    refreshed, links, changed = await refresh_summary_event_links(content, repo)

    assert changed is True
    assert "[新标题] - [abcdef12]" in refreshed
    assert "*After Alice sent" in refreshed
    assert "[未变化] - [deadbeef]" in refreshed
    assert links[0].resolved is True
    assert links[0].event_id == "abcdef123456"
    assert links[1].resolved is False


@pytest.mark.asyncio
async def test_refresh_summary_files_for_event_persists_referenced_file(tmp_path: Path) -> None:
    repo = InMemoryEventRepository()
    event_id = "1234567890abcdef"
    await repo.upsert(Event(event_id=event_id, topic="重跑后的标题"))
    summary_path = tmp_path / "groups" / "g1" / "summaries" / "2026-05-22.md"
    summary_path.parent.mkdir(parents=True)
    summary_path.write_text("[事件列表]\n[旧标题] - [12345678]\n", encoding="utf-8")

    updated = await refresh_summary_files_for_event(tmp_path, repo, event_id)

    assert updated == 1
    assert "[重跑后的标题] - [12345678]" in summary_path.read_text(encoding="utf-8")
