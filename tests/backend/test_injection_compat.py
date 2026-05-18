"""Tests for core/utils/injection_compat.py — Phase 6 injection adapter."""
import pytest
from core.utils.injection_compat import resolve_injection_position


# ---------------------------------------------------------------------------
# resolve_injection_position — unit tests
# ---------------------------------------------------------------------------

class TestResolveInjectionPosition:

    # ── Non-fake_tool_call positions pass through unchanged ─────────────────

    def test_system_prompt_unchanged(self):
        pos, reason = resolve_injection_position("gpt-4o", "system_prompt")
        assert pos == "system_prompt"
        assert reason == ""

    def test_user_message_before_unchanged(self):
        pos, reason = resolve_injection_position("o1-mini", "user_message_before")
        assert pos == "user_message_before"
        assert reason == ""

    def test_user_message_after_unchanged(self):
        pos, reason = resolve_injection_position(None, "user_message_after")
        assert pos == "user_message_after"
        assert reason == ""

    # ── No model info → keep configured position ────────────────────────────

    def test_no_model_keeps_fake_tool_call(self):
        pos, reason = resolve_injection_position(None, "fake_tool_call")
        assert pos == "fake_tool_call"
        assert reason == ""

    def test_empty_string_model_keeps_fake_tool_call(self):
        pos, reason = resolve_injection_position("", "fake_tool_call")
        assert pos == "fake_tool_call"
        assert reason == ""

    # ── Compatible model → fake_tool_call kept ──────────────────────────────

    def test_gpt4o_keeps_fake_tool_call(self):
        pos, reason = resolve_injection_position("gpt-4o", "fake_tool_call")
        assert pos == "fake_tool_call"
        assert reason == ""

    def test_claude_keeps_fake_tool_call(self):
        pos, reason = resolve_injection_position("claude-3-5-sonnet-20241022", "fake_tool_call")
        assert pos == "fake_tool_call"
        assert reason == ""

    def test_deepseek_keeps_fake_tool_call(self):
        pos, reason = resolve_injection_position("deepseek-chat", "fake_tool_call")
        assert pos == "fake_tool_call"
        assert reason == ""

    # ── Incompatible models → downgrade to user_message_before ──────────────

    def test_o1_downgrades(self):
        pos, reason = resolve_injection_position("o1", "fake_tool_call")
        assert pos == "user_message_before"
        assert reason != ""

    def test_o1_mini_downgrades(self):
        pos, reason = resolve_injection_position("o1-mini", "fake_tool_call")
        assert pos == "user_message_before"
        assert reason != ""

    def test_o3_downgrades(self):
        pos, reason = resolve_injection_position("o3", "fake_tool_call")
        assert pos == "user_message_before"
        assert reason != ""

    def test_o3_mini_downgrades(self):
        pos, reason = resolve_injection_position("o3-mini", "fake_tool_call")
        assert pos == "user_message_before"
        assert reason != ""

    def test_gemini_pro_downgrades(self):
        pos, reason = resolve_injection_position("gemini-1.5-pro", "fake_tool_call")
        assert pos == "user_message_before"
        assert reason != ""

    def test_gemini_flash_downgrades(self):
        pos, reason = resolve_injection_position("gemini-2.0-flash", "fake_tool_call")
        assert pos == "user_message_before"
        assert reason != ""

    def test_gemini_case_insensitive(self):
        pos, reason = resolve_injection_position("Gemini-Pro", "fake_tool_call")
        assert pos == "user_message_before"

    def test_o_series_case_insensitive(self):
        pos, reason = resolve_injection_position("O1-mini", "fake_tool_call")
        assert pos == "user_message_before"

    # ── Downgrade does not change non-fake_tool_call configured values ───────

    def test_incompatible_model_with_system_prompt_unchanged(self):
        """Even an incompatible model should NOT change system_prompt."""
        pos, reason = resolve_injection_position("o1-mini", "system_prompt")
        assert pos == "system_prompt"
        assert reason == ""

    def test_incompatible_model_with_user_message_before_unchanged(self):
        pos, reason = resolve_injection_position("gemini-pro", "user_message_before")
        assert pos == "user_message_before"
        assert reason == ""

    # ── Reason string content ────────────────────────────────────────────────

    def test_downgrade_reason_is_nonempty_string(self):
        _, reason = resolve_injection_position("o1", "fake_tool_call")
        assert isinstance(reason, str)
        assert len(reason) > 5

    def test_compatible_reason_is_empty_string(self):
        _, reason = resolve_injection_position("gpt-4o", "fake_tool_call")
        assert reason == ""
