from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from core.config import PluginConfig
from core.event_handler import EventHandler, _prepend_to_result, _response_text
from core.plugin_initializer import PluginInitializer
from core.utils.frontend_build import _render_redirect_page


class _Event:
    unified_msg_origin = "session-1"

    def get_group_id(self) -> str:
        return "group-1"


class _Router:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def process(self, **kwargs) -> None:
        self.calls.append(kwargs)


def test_prepend_to_result_uses_message_event_result_chain() -> None:
    result = SimpleNamespace(chain=[])

    _prepend_to_result(result, "debug prefix")

    assert len(result.chain) == 1
    assert result.chain[0].text == "debug prefix"


def test_response_text_supports_completion_text_and_legacy_text() -> None:
    assert _response_text(SimpleNamespace(completion_text="new")) == "new"
    assert _response_text(SimpleNamespace(text="legacy")) == "legacy"
    assert _response_text(SimpleNamespace(completion_text="", text="fallback")) == "fallback"
    assert _response_text(SimpleNamespace()) == ""


async def test_handle_llm_response_records_completion_text() -> None:
    router = _Router()
    handler = EventHandler(SimpleNamespace(router=router))

    await handler.handle_llm_response(_Event(), SimpleNamespace(completion_text="bot reply"))

    assert len(router.calls) == 1
    assert router.calls[0]["text"] == "bot reply"
    assert router.calls[0]["raw_group_id"] == "group-1"


async def test_handle_llm_response_records_legacy_text() -> None:
    router = _Router()
    handler = EventHandler(SimpleNamespace(router=router))

    await handler.handle_llm_response(_Event(), SimpleNamespace(text="old bot reply"))

    assert len(router.calls) == 1
    assert router.calls[0]["text"] == "old bot reply"


async def test_handle_decorating_result_adds_debug_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    class Recall:
        def pop_recall_debug(self, session_id: str) -> dict:
            assert session_id == "session-1"
            return {
                "query": "query",
                "granularity": "both",
                "total": 1,
                "events": [{"topic": "topic", "type": "narrative"}],
                "position": "system_prompt",
            }

    class Result(list):
        def is_llm_result(self) -> bool:
            return True

    init = SimpleNamespace(
        recall=Recall(),
        cfg=PluginConfig({"show_thinking_process": True, "show_system_prompt": True}),
    )
    handler = EventHandler(init)
    handler._pre_inject_sys_prompt["session-1"] = (
        "base\n<!-- EM:MEMORY:START -->memory<!-- EM:MEMORY:END -->"
    )
    result = Result(["normal reply"])

    monkeypatch.setattr(
        "core.event_handler._prepend_to_result",
        lambda current_result, text: current_result.insert(0, text),
    )

    await handler.handle_decorating_result(_Event(), result)

    assert result[0].startswith("[系统测试消息]")
    assert "[Moirai 记忆检索]" in result[0]
    assert "[System Prompt" in result[0]
    assert "base" in result[0]
    assert "memory" not in result[0]


def test_plugin_initializer_cfg_reads_runtime_overrides(tmp_path) -> None:
    (tmp_path / "plugin_config.json").write_text(
        json.dumps({"show_thinking_process": True}),
        encoding="utf-8",
    )
    star = SimpleNamespace(config={"debug": {"show_system_prompt": True}})
    initializer = PluginInitializer(
        context=SimpleNamespace(),
        cfg=PluginConfig({"show_thinking_process": False, "show_system_prompt": False}),
        data_dir=tmp_path,
        star=star,
    )

    icfg = initializer.cfg.get_injection_config()

    assert icfg.show_thinking_process is True
    assert icfg.show_system_prompt is True


def test_redirect_page_uses_real_links_without_popup_interception() -> None:
    html = _render_redirect_page(2666)

    assert 'href="http://127.0.0.1:2666"' in html
    assert 'id="top-link"' in html
    assert 'href="#"' not in html
    assert "preventDefault" not in html
    assert "window.open" not in html
