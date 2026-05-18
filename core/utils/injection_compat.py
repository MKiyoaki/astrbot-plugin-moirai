"""Injection compatibility adapter.

Resolves the effective injection position at runtime so that `fake_tool_call`
can be automatically downgraded for LLM providers/models that reject
synthetic tool-call messages in context.

The adapter is intentionally conservative:
- Only downgrades when the model name matches a *known* incompatible pattern.
- Falls back to the configured position when model info is unavailable.
- Never upgrades (e.g. won't switch user_message_before → fake_tool_call).
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Known-incompatible model patterns
# Each entry: (compiled regex, fallback_position, human-readable reason)
# ---------------------------------------------------------------------------
_INCOMPATIBLE: list[tuple[re.Pattern[str], str, str]] = [
    # OpenAI o-series reasoning models — tool-call context not supported in
    # the same way; these models use a different message flow.
    (re.compile(r"^o\d", re.IGNORECASE), "user_message_before",
     "o-series reasoning model does not support synthetic tool-call context"),

    # Gemini models accessed via OpenAI-compatible wrappers may reject
    # assistant tool-call shaped messages.
    (re.compile(r"^gemini", re.IGNORECASE), "user_message_before",
     "Gemini model may reject synthetic tool-call context via OpenAI adapter"),
]


def resolve_injection_position(
    model: str | None,
    configured: str,
) -> tuple[str, str]:
    """Return (effective_position, reason).

    Parameters
    ----------
    model:
        The model name from ``ProviderRequest.model``.  May be ``None`` when
        the provider does not set it.
    configured:
        The position value from ``InjectionConfig.position``.

    Returns
    -------
    effective_position:
        The position that should actually be used for injection.
    reason:
        A short human-readable explanation.  Empty string when no change.
    """
    if configured != "fake_tool_call":
        return configured, ""

    if not model:
        return configured, ""

    for pattern, fallback, reason in _INCOMPATIBLE:
        if pattern.match(model):
            return fallback, reason

    return configured, ""
