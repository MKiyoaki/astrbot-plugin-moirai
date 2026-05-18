import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from core.event_handler import EventHandler

@pytest.fixture
def event_handler():
    init = MagicMock()
    # recall has both async and sync methods
    recall = MagicMock()
    recall.recall_and_inject = AsyncMock()
    recall.pop_recall_debug = MagicMock()
    recall.pop_injection_debug = MagicMock()
    init.recall = recall
    
    # router is mostly async but some sync methods
    router = MagicMock()
    router.process = AsyncMock()
    router.flush_window_split_tail = AsyncMock()
    router.note_session_persona = MagicMock()
    init.router = router
    
    init.resolver = MagicMock()
    init.resolver.get_or_create_uid = AsyncMock()
    
    init.cfg = MagicMock()
    init.context_manager = MagicMock()
    init.context_manager.update_state = MagicMock()
    
    # Mock injection config
    icfg = MagicMock()
    icfg.show_thinking_process = True
    icfg.show_system_prompt = True
    icfg.show_injection_summary = True
    init.cfg.get_injection_config.return_value = icfg
    
    return EventHandler(init), init

def make_astr_event(msg="hello", umo="u1"):
    event = MagicMock()
    event.message_str = msg
    event.unified_msg_origin = umo
    event.get_platform_name.return_value = "qq"
    event.get_sender_id.return_value = "123"
    event.get_sender_name.return_value = "Alice"
    event.get_group_id.return_value = "g1"
    event.created_at = 1000.0
    return event

@pytest.mark.asyncio
async def test_handle_message(event_handler):
    eh, init = event_handler
    event = make_astr_event()
    
    await eh.handle_message(event)
    
    init.router.process.assert_called_once()
    args = init.router.process.call_args.kwargs
    assert args["platform"] == "qq"
    assert args["text"] == "hello"
    assert args["raw_group_id"] == "g1"

@pytest.mark.asyncio
async def test_handle_llm_request(event_handler):
    eh, init = event_handler
    event = make_astr_event()
    req = MagicMock()
    req.prompt = "hello"
    req.system_prompt = "Existing"
    
    init.recall.recall_and_inject.return_value = 1
    init.resolver.get_or_create_uid.return_value = "u1"
    
    await eh.handle_llm_request(event, req)
    
    init.recall.recall_and_inject.assert_called_once()
    init.context_manager.update_state.assert_called_once()

@pytest.mark.asyncio
async def test_handle_llm_response(event_handler):
    eh, init = event_handler
    event = make_astr_event()
    resp = MagicMock()
    resp.completion_text = "Bot reply"
    
    # Pre-set persona name in internal dict
    eh._pre_inject_persona_name["qq:g1"] = "AliceBot"
    
    await eh.handle_llm_response(event, resp)
    
    init.router.process.assert_called_once()
    args = init.router.process.call_args.kwargs
    assert args["platform"] == "internal"
    assert args["text"] == "Bot reply"
    assert args["display_name"] == "AliceBot"

@pytest.mark.asyncio
async def test_handle_decorating_result(event_handler):
    eh, init = event_handler
    event = make_astr_event()
    result = MagicMock()
    result.chain = []
    
    # Mock LLM result - simulate the check in _is_llm_like_result
    result.is_llm_result.return_value = True
    result.result_content_type.name = "LLM_RESULT"
    
    # Mock recall debug info
    init.recall.pop_recall_debug.return_value = {
        "query": "test", "granularity": "both", "total": 1, 
        "events": [{"topic": "ev1", "type": "episode"}], "position": "system_prompt"
    }
    init.recall.pop_injection_debug.return_value = {
        "injected": True, 
        "memory": {"injected": True, "count": 1, "events": [{"topic": "ev1", "type": "episode"}]}
    }
    
    await eh.handle_decorating_result(event, result)
    
    assert len(result.chain) > 0
    debug_text = result.chain[0].text
    assert "[系统测试消息]" in debug_text
    assert "[Moirai 记忆检索]" in debug_text
