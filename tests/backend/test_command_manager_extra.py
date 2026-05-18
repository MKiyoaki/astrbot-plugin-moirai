import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch
from core.managers.command_manager import CommandManager
from core.domain.models import Persona, Impression, Event

@pytest.fixture
def command_manager():
    scheduler = MagicMock()
    scheduler.task_names = ["daily_maintenance", "consolidated_maintenance"]
    recall = AsyncMock()
    context_manager = MagicMock()
    persona_repo = AsyncMock()
    event_repo = AsyncMock()
    impression_repo = AsyncMock()
    
    return CommandManager(
        scheduler=scheduler,
        recall=recall,
        context_manager=context_manager,
        persona_repo=persona_repo,
        event_repo=event_repo,
        impression_repo=impression_repo
    ), scheduler, recall, context_manager, persona_repo, event_repo, impression_repo

@pytest.mark.asyncio
async def test_persona_command(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    pr.get_by_identity.return_value = Persona("u1", [("qq", "123")], "Alice", {"description": "test desc"}, 0.8, 0.0, 0.0)
    
    res = await cm.persona("qq", "123")
    assert "Alice" in res
    assert "test desc" in res
    assert "80%" in res

@pytest.mark.asyncio
async def test_soul_command(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    from core.social.soul_state import SoulState
    soul_states = {"s1": SoulState(recall_depth=5.0, creativity=-2.0)}
    
    res = await cm.soul("s1", soul_states)
    assert "记忆检索驱动" in res
    assert "+5.0" in res
    assert "创意度" in res
    assert "-2.0" in res

@pytest.mark.asyncio
async def test_recall_command(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    recall.recall.return_value = [Event(event_id="e1", topic="topic1")]
    
    res = await cm.recall("query")
    assert "topic1" in res

@pytest.mark.asyncio
async def test_run_task_command(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    sched.run_now = AsyncMock(return_value=True)
    
    res = await cm.run_task("decay")
    assert "triggered" in res or "已触发" in res
    sched.run_now.assert_called_with("daily_maintenance")
    
    sched.run_now = AsyncMock(return_value=False)
    res = await cm.run_task("unknown")
    assert "not found" in res or "未找到" in res

@pytest.mark.asyncio
async def test_flush_command(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    window = MagicMock()
    window.messages = [1, 2, 3]
    ctx.pop_window.return_value = window
    
    res = await cm.flush("s1")
    assert "3" in res
    ctx.pop_window.assert_called_with("s1")

@pytest.mark.asyncio
async def test_webui_command(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    webui = AsyncMock()
    cm._webui = webui
    
    res = await cm.webui("on")
    assert "started" in res or "已启动" in res
    webui.start.assert_called_once()
    
    res = await cm.webui("off")
    assert "stopped" in res or "已停止" in res or "已关闭" in res
    webui.stop.assert_called_once()

@pytest.mark.asyncio
async def test_set_language(command_manager, tmp_path):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    cm._data_dir = tmp_path
    
    res = await cm.set_language("en")
    assert "English" in res
    assert cm._lang == "en-US"
    
    res = await cm.set_language("zh")
    assert "中文" in res
    assert cm._lang == "zh-CN"

@pytest.mark.asyncio
async def test_reset_here_confirmation(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    er.delete_by_group.return_value = 5
    
    # First call - confirmation
    res = await cm.reset_here("s1", "g1")
    assert "确认" in res or "confirm" in res
    
    # Second call - actual execution
    res = await cm.reset_here("s1", "g1")
    assert "5" in res
    er.delete_by_group.assert_called_with("g1")

@pytest.mark.asyncio
async def test_reset_all_confirmation(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    er.delete_all.return_value = 10
    pr.list_all.return_value = [Persona("u1", [], "Alice", {}, 0.5, 0.0, 0.0)]
    
    # First call
    res = await cm.reset_all("s1")
    assert "确认" in res
    
    # Second call
    res = await cm.reset_all("s1")
    assert "10" in res
    er.delete_all.assert_called_once()
    pr.delete.assert_called_once()

@pytest.mark.asyncio
async def test_help_command(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    res = await cm.help()
    assert "帮助" in res or "Help" in res

@pytest.mark.asyncio
async def test_reset_persona_all_confirmation(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    pr.list_all.return_value = [Persona("u1", [], "Alice", {}, 0.5, 0.0, 0.0)]
    
    # First call
    res = await cm.reset_persona_all("s1")
    assert "确认" in res
    
    # Second call
    res = await cm.reset_persona_all("s1")
    assert "1" in res
    pr.delete.assert_called_once()

@pytest.mark.asyncio
async def test_reset_event_by_group_confirmation(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    er.delete_by_group.return_value = 3
    
    # First call
    res = await cm.reset_event_by_group("s1", "g1")
    assert "确认" in res
    
    # Second call
    res = await cm.reset_event_by_group("s1", "g1")
    assert "3" in res
    er.delete_by_group.assert_called_with("g1")

@pytest.mark.asyncio
async def test_reset_persona_one_confirmation(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    pr.get_by_identity.return_value = Persona("u1", [], "Alice", {}, 0.5, 0.0, 0.0)
    
    # First call
    res = await cm.reset_persona_one("s1", "qq", "123")
    assert "确认" in res
    
    # Second call
    res = await cm.reset_persona_one("s1", "qq", "123")
    assert "Alice" in res
    pr.delete.assert_called_once()

@pytest.mark.asyncio
async def test_install_dependency_invalid(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    res = await cm.install_dependency("invalid-lib", MagicMock())
    assert "不支持" in res or "invalid" in res

@pytest.mark.asyncio
async def test_install_dependency_success(command_manager):
    cm, sched, recall, ctx, pr, er, ir = command_manager
    
    with patch("asyncio.create_subprocess_exec") as mock_exec:
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"success", b"")
        mock_proc.returncode = 0
        mock_exec.return_value = mock_proc
        
        res = await cm.install_dependency("scikit-learn", MagicMock())
        assert "安装成功" in res or "installed" in res
