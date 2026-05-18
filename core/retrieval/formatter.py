# Re-export from core.utils.formatter for backward compatibility.
# Import directly from core.utils.formatter in new code.
from ..utils.formatter import (
    format_events_for_fake_tool_call,
    format_events_for_prompt,
    format_events_for_prompt_safe,
)

__all__ = [
    "format_events_for_prompt",
    "format_events_for_prompt_safe",
    "format_events_for_fake_tool_call",
]
