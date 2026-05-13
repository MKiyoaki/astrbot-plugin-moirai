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

_ROOT = Path(__file__).parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.utils.version import get_plugin_version
from core.utils.frontend_build import build_frontend
from web.server import WebuiServer, _DEMO_SUMMARY_1, _DEMO_SUMMARY_2
from core.domain.models import Event, Impression, Persona, MessageRef
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

    personas = [
        Persona(
            uid="demo_uid_alice",
            bound_identities=[("qq", "demo_10001")],
            primary_name="Alice",
            persona_attrs={"description": "热情开朗，喜爱音乐与户外运动",
                           "affect_type": "积极", "content_tags": ["音乐", "徒步", "摄影"]},
            confidence=0.92,
            created_at=now - 45 * DAY,
            last_active_at=now - DAY,
        ),
        Persona(
            uid="demo_uid_bob",
            bound_identities=[("qq", "demo_10002")],
            primary_name="Bob",
            persona_attrs={"description": "资深开发者，逻辑严密但乐于助人",
                           "affect_type": "中性", "content_tags": ["Python", "架构", "AI"]},
            confidence=0.85,
            created_at=now - 40 * DAY,
            last_active_at=now - 2 * DAY,
        ),
        Persona(
            uid="demo_uid_charlie",
            bound_identities=[("telegram", "demo_tg_charlie")],
            primary_name="Charlie",
            persona_attrs={"description": "数据分析师，喜欢分享科技资讯",
                           "affect_type": "积极", "content_tags": ["科技", "阅读", "旅行"]},
            confidence=0.78,
            created_at=now - 20 * DAY,
            last_active_at=now - 5 * DAY,
        ),
        Persona(
            uid="demo_uid_diana",
            bound_identities=[("internal", "diana_web")],
            primary_name="Diana",
            persona_attrs={"description": "文学爱好者，对话风格温婉",
                           "affect_type": "积极", "content_tags": ["文学", "诗歌", "艺术"]},
            confidence=0.72,
            created_at=now - 10 * DAY,
            last_active_at=now - 12 * 3600,
        ),
        Persona(
            uid="demo_uid_bot",
            bound_identities=[("internal", "bot")],
            primary_name="BOT",
            persona_attrs={"description": "搭载增强记忆引擎的智能助手",
                           "affect_type": "中性", "content_tags": ["记忆管理", "日程分析"]},
            confidence=1.0,
            created_at=now - 90 * DAY,
            last_active_at=now,
        ),
    ]

    events = [
        Event(
            event_id="demo_evt_001", group_id="demo_group_001",
            start_time=now - 10 * DAY, end_time=now - 10 * DAY + 1200,
            participants=["demo_uid_alice", "demo_uid_bob", "demo_uid_bot"],
            interaction_flow=[
                MessageRef("demo_uid_alice", now - 10 * DAY, "h1", "大家早安！"),
                MessageRef("demo_uid_bob", now - 10 * DAY + 60, "h2", "早，Alice。"),
            ],
            topic="早安问候",
            summary="Alice 发起早安问候，Bob 礼貌回应，群组开启了一天的活跃氛围。",
            chat_content_tags=["日常", "社交"],
            salience=0.3, confidence=0.95, inherit_from=[],
            last_accessed_at=now - 5 * DAY,
        ),
        Event(
            event_id="demo_evt_002", group_id="demo_group_001",
            start_time=now - 8 * DAY, end_time=now - 8 * DAY + 3600,
            participants=["demo_uid_alice", "demo_uid_bob", "demo_uid_bot"],
            interaction_flow=[],
            topic="音乐推荐：古典乐之美",
            summary="Alice 分享了几首德彪西的曲目，Bob 探讨了古典乐对专注力的提升作用。",
            chat_content_tags=["艺术", "古典乐", "分享"],
            salience=0.65, confidence=0.88, inherit_from=["demo_evt_001"],
            last_accessed_at=now - 2 * DAY,
        ),
        Event(
            event_id="demo_evt_003", group_id="demo_group_001",
            start_time=now - 6 * DAY, end_time=now - 6 * DAY + 5400,
            participants=["demo_uid_bob", "demo_uid_charlie", "demo_uid_bot"],
            interaction_flow=[],
            topic="异步 IO 性能调优",
            summary="Bob 与 Charlie 深入讨论了 Python asyncio 的事件循环机制及在高并发场景下的优化策略。",
            chat_content_tags=["技术", "Python", "调优"],
            salience=0.82, confidence=0.94, inherit_from=[],
            last_accessed_at=now - 12 * 3600,
        ),
        Event(
            event_id="demo_evt_004", group_id="demo_group_002",
            start_time=now - 4 * DAY, end_time=now - 4 * DAY + 2400,
            participants=["demo_uid_alice", "demo_uid_diana", "demo_uid_bot"],
            interaction_flow=[],
            topic="周末徒步计划",
            summary="Alice 邀请 Diana 周末去西山徒步，Diana 建议携带专业摄影器材记录秋景。",
            chat_content_tags=["运动", "徒步", "摄影"],
            salience=0.58, confidence=0.85, inherit_from=[],
            last_accessed_at=now - DAY,
        ),
        Event(
            event_id="demo_evt_005", group_id=None,
            start_time=now - 2 * DAY, end_time=now - 2 * DAY + 900,
            participants=["demo_uid_bob", "demo_uid_bot"],
            interaction_flow=[],
            topic="私聊：核心架构咨询",
            summary="Bob 私下向 BOT 询问了增强记忆引擎的向量检索原理，表现出对底层实现的浓厚兴趣。",
            chat_content_tags=["技术", "咨询", "私聊"],
            salience=0.75, confidence=0.89, inherit_from=["demo_evt_003"],
            last_accessed_at=now - 3600,
        ),
        Event(
            event_id="demo_evt_006", group_id="demo_group_001",
            start_time=now - DAY, end_time=now - DAY + 4200,
            participants=["demo_uid_alice", "demo_uid_bob", "demo_uid_charlie", "demo_uid_bot"],
            interaction_flow=[],
            topic="AI 伦理与长期记忆",
            summary="群组讨论了机器人拥有长期记忆后可能带来的隐私风险及相关的伦理边界问题。",
            chat_content_tags=["AI", "伦理", "深度讨论"],
            salience=0.91, confidence=0.92, inherit_from=[],
            last_accessed_at=now,
            is_locked=True,
        ),
        Event(
            event_id="demo_evt_007", group_id="demo_group_002",
            start_time=now - 18 * 3600, end_time=now - 17 * 3600,
            participants=["demo_uid_diana", "demo_uid_bot"],
            interaction_flow=[],
            topic="现代诗歌鉴赏",
            summary="Diana 朗读了一首关于时间的诗，BOT 从语义角度给出了深刻的解读与回应。",
            chat_content_tags=["文学", "诗歌", "艺术"],
            salience=0.42, confidence=0.81, inherit_from=[],
            last_accessed_at=now - 6 * 3600,
        ),
        Event(
            event_id="demo_evt_008", group_id="demo_group_001",
            start_time=now - 6 * 3600, end_time=now - 5 * 3600,
            participants=["demo_uid_alice", "demo_uid_bob", "demo_uid_bot"],
            interaction_flow=[],
            topic="项目周报同步",
            summary="Alice 汇总了本周的讨论热点，Bob 确认了技术分享的排期，群组达成阶段性一致。",
            chat_content_tags=["工作", "同步", "周报"],
            salience=0.67, confidence=0.88, inherit_from=["demo_evt_006"],
            last_accessed_at=now,
        ),
    ]

    for p in personas: await persona_repo.upsert(p)
    for e in events: await event_repo.upsert(e)

    impressions = [
        Impression(
            observer_uid="demo_uid_bot", subject_uid="demo_uid_alice",
            ipc_orientation="友好", benevolence=0.85, power=0.1,
            affect_intensity=0.6, r_squared=0.88, confidence=0.92,
            scope="global",
            evidence_event_ids=["demo_evt_001", "demo_evt_002", "demo_evt_004", "demo_evt_006"],
            last_reinforced_at=now - 12 * 3600,
        ),
        Impression(
            observer_uid="demo_uid_bot", subject_uid="demo_uid_bob",
            ipc_orientation="支配友好", benevolence=0.3, power=0.45,
            affect_intensity=0.38, r_squared=0.75, confidence=0.89,
            scope="global",
            evidence_event_ids=["demo_evt_001", "demo_evt_003", "demo_evt_005", "demo_evt_006", "demo_evt_008"],
            last_reinforced_at=now - 3600,
        ),
        Impression(
            observer_uid="demo_uid_bot", subject_uid="demo_uid_charlie",
            ipc_orientation="友好", benevolence=0.4, power=-0.1,
            affect_intensity=0.25, r_squared=0.65, confidence=0.81,
            scope="demo_group_001",
            evidence_event_ids=["demo_evt_003", "demo_evt_006"],
            last_reinforced_at=now - DAY,
        ),
        Impression(
            observer_uid="demo_uid_bot", subject_uid="demo_uid_diana",
            ipc_orientation="友好", benevolence=0.65, power=-0.2,
            affect_intensity=0.42, r_squared=0.81, confidence=0.85,
            scope="demo_group_002",
            evidence_event_ids=["demo_evt_004", "demo_evt_007"],
            last_reinforced_at=now - 6 * 3600,
        ),
        Impression(
            observer_uid="demo_uid_alice", subject_uid="demo_uid_bot",
            ipc_orientation="友好", benevolence=0.9, power=0.0,
            affect_intensity=0.65, r_squared=0.92, confidence=0.85,
            scope="global",
            evidence_event_ids=["demo_evt_001", "demo_evt_002"],
            last_reinforced_at=now - DAY,
        ),
        Impression(
            observer_uid="demo_uid_bob", subject_uid="demo_uid_alice",
            ipc_orientation="友好", benevolence=0.55, power=0.1,
            affect_intensity=0.4, r_squared=0.78, confidence=0.75,
            scope="demo_group_001",
            evidence_event_ids=["demo_evt_002"],
            last_reinforced_at=now - 8 * DAY,
        ),
        Impression(
            observer_uid="demo_uid_diana", subject_uid="demo_uid_alice",
            ipc_orientation="友好", benevolence=0.75, power=0.0,
            affect_intensity=0.5, r_squared=0.85, confidence=0.82,
            scope="demo_group_002",
            evidence_event_ids=["demo_evt_004"],
            last_reinforced_at=now - 4 * DAY,
        ),
    ]
    for i in impressions: await impression_repo.upsert(i)

    for date, content in [("2026-05-01", _DEMO_SUMMARY_1), ("2026-05-02", _DEMO_SUMMARY_2)]:
        path = data_dir / "groups" / "demo_group_001" / "summaries" / f"{date}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    print(f"  演示数据: 已注入（{len(personas)} 人格 / {len(events)} 事件 / {len(impressions)} 印象 / 2 摘要）")


async def main() -> None:
    port = _parse_port()
    data_dir = _DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)

    if not build_frontend():
        print("  ⚠ 前端构建失败，请检查 Node.js 环境后重试。")
        return

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
        plugin_version=get_plugin_version(),
    )
    await srv.start()

    print(f"\n  Enhanced Memory — 调试界面已启动")
    print(f"  http://localhost:{port}/?token=dev")
    print(f"  数据目录: {data_dir}")
    print(f"  认证: 已关闭（本地调试模式）")

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
