from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from core.config import PluginConfig
from core.event_handler import (
    EventHandler,
    _extract_system_prompt_skill_names,
    _format_injection_debug_for_display,
    _format_system_prompt_for_debug,
    _is_llm_like_result,
    _prepend_to_result,
    _response_text,
)
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


def test_format_system_prompt_debug_compacts_persona_and_skills() -> None:
    raw = (
        "prefix\n"
        "# Persona Instructions\n\n"
        "You are a very long persona.\n"
        "Do not show this content.\n\n"
        "## Skills\n"
        "You have many useful skills that can help you accomplish various tasks.\n"
        "### Available skills\n"
        "- code_formatter: format code (file: skills/code_formatter/SKILL.md)\n"
        "- web_search: search docs (file: skills/web_search/SKILL.md)\n"
        "### Skill Rules\n"
        "- Discovery: do not show this rule.\n"
        "## Tools\n"
        "keep this section"
    )

    text = _format_system_prompt_for_debug(raw, "DefaultPersona")

    assert "prefix" not in text  # whitelist: non-heading raw content is not emitted
    assert "Persona Instruction：DefaultPersona" in text
    assert "You are a very long persona" not in text
    assert "## Skills" not in text
    assert "Available skills" not in text
    assert "Skill Rules" not in text
    assert "format code" not in text
    assert "已启用 Skill：code_formatter, web_search" in text
    assert "Discovery" not in text
    # Unrecognized heading sections are now skipped entirely
    assert "## Tools" not in text
    assert "keep this section" not in text


def test_format_system_prompt_debug_outputs_fixed_summary_without_prompt_blocks() -> None:
    text = _format_system_prompt_for_debug("", "DefaultPersona", ["code_formatter"])

    assert text == "Persona Instruction：DefaultPersona\n已启用 Skill：code_formatter"


def test_extract_system_prompt_skill_names_ignores_skill_rules() -> None:
    raw = (
        "## Skills\n"
        "intro\n"
        "### Available skills\n"
        "- code_formatter: format code (file: skills/code_formatter/SKILL.md)\n"
        "- web_search: search docs (file: skills/web_search/SKILL.md)\n"
        "### Skill Rules\n"
        "- Discovery: do not show this rule.\n"
        "- Trigger rules: do not show this rule.\n"
    )

    assert _extract_system_prompt_skill_names(raw) == ["code_formatter", "web_search"]


def test_format_injection_debug_hides_internal_prompt_details() -> None:
    text = _format_injection_debug_for_display(
        {
            "position": "system_prompt",
            "injected": True,
            "memory": {
                "injected": True,
                "count": 1,
                "events": [
                    {
                        "label": "叙事",
                        "topic": "学习压力",
                        "summary": "用户近期多次提到课程压力。",
                    }
                ],
            },
            "persona": {
                "name": "Alice",
                "dimensions": [
                    {"label": "开放性", "percent": 72},
                    {"label": "神经质", "percent": 69},
                ],
            },
            "soul": {"recall_depth": 2.5, "impression_depth": 0.0, "expression_desire": 0.8, "creativity": 0.2},
            "hidden": ["完整 System Prompt", "后台任务 prompt", "Big Five evidence 原文"],
        }
    )

    assert "[Moirai 实际注入摘要]" in text
    assert "学习压力：用户近期多次提到课程压力。" in text
    assert "开放性 72%" in text
    assert "神经质 69%" in text
    assert "recall_depth=2.5" in text
    assert "Big Five evidence 原文" in text
    assert "完整画像 prompt 的正文" not in text
    assert "Skill Rules" not in text


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
        "base\n"
        "# Persona Instructions\n\nYou are a helpful assistant.\n"
        "## Skills\n- search: search the web\n"
        "<!-- EM:MEMORY:START -->memory<!-- EM:MEMORY:END -->"
    )
    handler._pre_inject_persona_name["session-1"] = "TestPersona"
    result = Result(["normal reply"])

    monkeypatch.setattr(
        "core.event_handler._prepend_to_result",
        lambda current_result, text: current_result.insert(0, text),
    )

    await handler.handle_decorating_result(_Event(), result)

    assert result[0].startswith("[系统测试消息]")
    assert "[Moirai 记忆检索]" in result[0]
    assert "[System Prompt" in result[0]
    # Whitelist: only persona name and skill names; raw content excluded
    assert "Persona Instruction：TestPersona" in result[0]
    assert "已启用 Skill：search" in result[0]
    assert "You are a helpful assistant" not in result[0]
    assert "memory" not in result[0]


async def test_handle_decorating_result_adds_injection_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    class Recall:
        def pop_injection_debug(self, session_id: str) -> dict:
            assert session_id == "session-1"
            return {
                "position": "system_prompt",
                "injected": True,
                "memory": {
                    "injected": True,
                    "count": 1,
                    "events": [{"label": "情节", "topic": "topic", "summary": "summary"}],
                },
                "persona": {
                    "name": "Alice",
                    "dimensions": [{"label": "开放性", "percent": 75}],
                },
                "hidden": ["完整 System Prompt", "后台任务 prompt", "完整 Persona 内容", "Big Five evidence 原文"],
            }

    class Result(list):
        def is_llm_result(self) -> bool:
            return True

    init = SimpleNamespace(
        recall=Recall(),
        cfg=PluginConfig({"show_injection_summary": True}),
    )
    handler = EventHandler(init)
    result = Result(["normal reply"])

    monkeypatch.setattr(
        "core.event_handler._prepend_to_result",
        lambda current_result, text: current_result.insert(0, text),
    )

    await handler.handle_decorating_result(_Event(), result)

    assert result[0].startswith("[系统测试消息]")
    assert "[Moirai 实际注入摘要]" in result[0]
    assert "topic：summary" in result[0]
    assert "开放性 75%" in result[0]
    assert "完整 Persona 内容" in result[0]


async def test_handle_decorating_result_accepts_streaming_finish(monkeypatch: pytest.MonkeyPatch) -> None:
    class Recall:
        def pop_injection_debug(self, session_id: str) -> dict:
            assert session_id == "session-1"
            return {
                "memory": {"injected": False, "count": 0, "events": []},
                "persona": None,
                "soul": None,
            }

    class Result(list):
        result_content_type = SimpleNamespace(name="STREAMING_FINISH")

        def is_llm_result(self) -> bool:
            return False

    init = SimpleNamespace(
        recall=Recall(),
        cfg=PluginConfig({"show_injection_summary": True}),
    )
    handler = EventHandler(init)
    result = Result(["normal reply"])

    monkeypatch.setattr(
        "core.event_handler._prepend_to_result",
        lambda current_result, text: current_result.insert(0, text),
    )

    assert _is_llm_like_result(result) is True

    await handler.handle_decorating_result(_Event(), result)

    assert result[0].startswith("[系统测试消息]")
    assert "[Moirai 实际注入摘要]" in result[0]


def test_plugin_initializer_cfg_reads_runtime_overrides(tmp_path) -> None:
    (tmp_path / "plugin_config.json").write_text(
        json.dumps({"show_thinking_process": True, "show_injection_summary": True}),
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
    assert icfg.show_injection_summary is True


def test_redirect_page_uses_real_links_without_popup_interception() -> None:
    html = _render_redirect_page(2666)

    assert 'href="http://127.0.0.1:2666"' in html
    assert 'id="top-link"' in html
    assert 'href="#"' not in html
    assert "preventDefault" not in html
    assert "window.open" not in html
