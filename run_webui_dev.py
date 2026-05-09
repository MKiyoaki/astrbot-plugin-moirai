"""本地 WebUI 调试启动脚本。

- 使用内存仓库，无需数据库文件
- 关闭认证（无需密码，直接进入界面）
- 自动注入演示数据（人格、事件、印象、摘要）
- 数据目录写在项目根下的 .dev_data/（重启后摘要文件保留，DB 数据不保留）
- 默认端口 2654，不与生产端口 2653 冲突

用法：
    python run_webui_dev.py
    python run_webui_dev.py --port 9000
"""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# 确保项目根在 sys.path 中（从任意目录运行时也能找到模块）
_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from web.server import WebuiServer, _DEMO_SUMMARY_1, _DEMO_SUMMARY_2
from core.domain.models import Event, Impression, Persona
from core.repository.memory import (
    InMemoryEventRepository,
    InMemoryImpressionRepository,
    InMemoryPersonaRepository,
)

_PORT = 2654
_DATA_DIR = _ROOT / ".dev_data"


def _parse_port() -> int:
    args = sys.argv[1:]
    if "--port" in args:
        idx = args.index("--port")
        try:
            return int(args[idx + 1])
        except (IndexError, ValueError):
            pass
    return _PORT


async def _seed(
    persona_repo: InMemoryPersonaRepository,
    event_repo: InMemoryEventRepository,
    impression_repo: InMemoryImpressionRepository,
    data_dir: Path,
) -> None:
    now = time.time()
    DAY = 86_400

    for p in [
        Persona(
            uid="demo_uid_alice",
            bound_identities=[("qq", "demo_10001")],
            primary_name="Alice",
            persona_attrs={"description": "热情开朗，喜爱音乐与游戏", "affect_type": "积极", "content_tags": ["音乐", "游戏", "聊天"]},
            confidence=0.88,
            created_at=now - 30 * DAY,
            last_active_at=now - DAY,
        ),
        Persona(
            uid="demo_uid_bob",
            bound_identities=[("qq", "demo_10002")],
            primary_name="Bob",
            persona_attrs={"description": "理性谨慎，热衷技术讨论", "affect_type": "中性", "content_tags": ["技术", "编程"]},
            confidence=0.82,
            created_at=now - 25 * DAY,
            last_active_at=now - 2 * DAY,
        ),
        Persona(
            uid="demo_uid_charlie",
            bound_identities=[("telegram", "demo_tg_charlie")],
            primary_name="Charlie",
            persona_attrs={"description": "神秘低调，偶尔参与讨论", "affect_type": "消极", "content_tags": ["旅行", "摄影"]},
            confidence=0.65,
            created_at=now - 15 * DAY,
            last_active_at=now - 5 * DAY,
        ),
        Persona(
            uid="demo_uid_bot",
            bound_identities=[("internal", "bot")],
            primary_name="BOT",
            persona_attrs={"description": "AI 助手", "affect_type": "中性", "content_tags": []},
            confidence=1.0,
            created_at=now - 60 * DAY,
            last_active_at=now,
        ),
    ]:
        await persona_repo.upsert(p)

    for e in [
        Event(
            event_id="demo_evt_001", group_id="demo_group_001",
            start_time=now - 7 * DAY, end_time=now - 7 * DAY + 1800,
            participants=["demo_uid_alice", "demo_uid_bob", "demo_uid_bot"],
            interaction_flow=[], topic="早安问候",
            chat_content_tags=["日常", "问候"],
            salience=0.45, confidence=0.82, inherit_from=[],
            last_accessed_at=now - DAY,
        ),
        Event(
            event_id="demo_evt_002", group_id="demo_group_001",
            start_time=now - 6 * DAY, end_time=now - 6 * DAY + 3600,
            participants=["demo_uid_alice", "demo_uid_bob", "demo_uid_bot"],
            interaction_flow=[], topic="音乐推荐",
            chat_content_tags=["音乐", "推荐", "文化"],
            salience=0.72, confidence=0.88, inherit_from=["demo_evt_001"],
            last_accessed_at=now - 12 * 3600,
        ),
        Event(
            event_id="demo_evt_003", group_id="demo_group_001",
            start_time=now - 5 * DAY, end_time=now - 5 * DAY + 2700,
            participants=["demo_uid_alice", "demo_uid_charlie", "demo_uid_bot"],
            interaction_flow=[], topic="游戏约定",
            chat_content_tags=["游戏", "约定", "娱乐"],
            salience=0.68, confidence=0.79, inherit_from=["demo_evt_002"],
            last_accessed_at=now - 8 * 3600,
        ),
        Event(
            event_id="demo_evt_004", group_id="demo_group_001",
            start_time=now - 3 * DAY, end_time=now - 3 * DAY + 4200,
            participants=["demo_uid_bob", "demo_uid_charlie", "demo_uid_bot"],
            interaction_flow=[], topic="技术交流",
            chat_content_tags=["技术", "编程", "讨论"],
            salience=0.85, confidence=0.91, inherit_from=["demo_evt_001"],
            last_accessed_at=now - 4 * 3600,
        ),
        Event(
            event_id="demo_evt_005", group_id=None,
            start_time=now - DAY, end_time=now - DAY + 900,
            participants=["demo_uid_alice", "demo_uid_bot"],
            interaction_flow=[], topic="私聊请教",
            chat_content_tags=["私聊", "帮助"],
            salience=0.55, confidence=0.77, inherit_from=[],
            last_accessed_at=now - 3600,
        ),
    ]:
        await event_repo.upsert(e)

    for imp in [
        Impression(
            observer_uid="demo_uid_bot", subject_uid="demo_uid_alice",
            ipc_orientation="友好", benevolence=0.7, power=0.0,
            affect_intensity=0.5, r_squared=0.8, confidence=0.85,
            scope="global",
            evidence_event_ids=["demo_evt_001", "demo_evt_002", "demo_evt_005"],
            last_reinforced_at=now - DAY,
        ),
        Impression(
            observer_uid="demo_uid_bot", subject_uid="demo_uid_bob",
            ipc_orientation="支配友好", benevolence=0.2, power=0.3,
            affect_intensity=0.25, r_squared=0.7, confidence=0.78,
            scope="global",
            evidence_event_ids=["demo_evt_001", "demo_evt_004"],
            last_reinforced_at=now - 2 * DAY,
        ),
        Impression(
            observer_uid="demo_uid_alice", subject_uid="demo_uid_bot",
            ipc_orientation="友好", benevolence=0.8, power=0.0,
            affect_intensity=0.6, r_squared=0.9, confidence=0.80,
            scope="global",
            evidence_event_ids=["demo_evt_001", "demo_evt_002"],
            last_reinforced_at=now - DAY,
        ),
        Impression(
            observer_uid="demo_uid_bob", subject_uid="demo_uid_alice",
            ipc_orientation="友好", benevolence=0.5, power=0.0,
            affect_intensity=0.35, r_squared=0.75, confidence=0.72,
            scope="demo_group_001",
            evidence_event_ids=["demo_evt_002"],
            last_reinforced_at=now - 6 * DAY,
        ),
        Impression(
            observer_uid="demo_uid_charlie", subject_uid="demo_uid_bob",
            ipc_orientation="友好", benevolence=0.0, power=0.0,
            affect_intensity=0.1, r_squared=0.5, confidence=0.60,
            scope="demo_group_001",
            evidence_event_ids=["demo_evt_004"],
            last_reinforced_at=now - 3 * DAY,
        ),
    ]:
        await impression_repo.upsert(imp)

    for date, content in [
        ("2026-05-01", _DEMO_SUMMARY_1),
        ("2026-05-02", _DEMO_SUMMARY_2),
    ]:
        path = data_dir / "groups" / "demo_group_001" / "summaries" / f"{date}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


async def main() -> None:
    port = _parse_port()
    data_dir = _DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    persona_repo    = InMemoryPersonaRepository()
    event_repo      = InMemoryEventRepository()
    impression_repo = InMemoryImpressionRepository()

    await _seed(persona_repo, event_repo, impression_repo, data_dir)

    srv = WebuiServer(
        persona_repo=persona_repo,
        event_repo=event_repo,
        impression_repo=impression_repo,
        data_dir=data_dir,
        port=port,
        auth_enabled=False,      # 本地调试无需密码
        plugin_version="dev",
    )
    await srv.start()

    print(f"\n  Enhanced Memory — 调试界面已启动")
    print(f"  http://localhost:{port}/?token=dev")
    print(f"  数据目录: {data_dir}")
    print(f"  认证: 已关闭（本地调试模式）")
    print(f"  演示数据: 已注入（4 人格 / 5 事件 / 5 印象 / 2 摘要）")
    print(f"\n  按 Ctrl+C 停止\n")

    stop_event = asyncio.Event()
    try:
        await stop_event.wait()   # 永久等待，直到 Ctrl+C
    except asyncio.CancelledError:
        pass
    finally:
        await srv.stop()
        print("已停止。")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
