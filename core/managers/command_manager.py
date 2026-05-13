"""CommandManager: handler logic for /mrm command group.

Delegates to the appropriate subsystem for each sub-command so that
main.py stays thin.  All methods return plain strings ready to send.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Awaitable, Callable

from ..utils.formatter import format_events_for_prompt
from ..utils.i18n import LANG_ZH, LANG_EN, LANG_JA, get_string

if TYPE_CHECKING:
    from ..managers.context_manager import ContextManager
    from ..managers.recall_manager import RecallManager
    from ..repository.base import EventRepository, PersonaRepository
    from ..tasks.scheduler import TaskScheduler

logger = logging.getLogger(__name__)

_DIM_NAMES = {
    LANG_ZH: {"O": "开放性", "C": "尽责性", "E": "外向性", "A": "宜人性", "N": "神经质"},
    LANG_EN: {"O": "Openness", "C": "Conscientiousness", "E": "Extraversion", "A": "Agreeableness", "N": "Neuroticism"},
    LANG_JA: {"O": "開放性", "C": "誠実性", "E": "外向性", "A": "協調性", "N": "神経症傾向"},
}
_CONFIRM_TTL = 30.0

_LANG_ALIASES = {
    "cn": LANG_ZH, "zh": LANG_ZH, "zh-cn": LANG_ZH, "chinese": LANG_ZH,
    "en": LANG_EN, "en-us": LANG_EN, "english": LANG_EN,
    "ja": LANG_JA, "jp": LANG_JA, "ja-jp": LANG_JA, "japanese": LANG_JA,
}
_LANG_DISPLAY = {LANG_ZH: "中文", LANG_EN: "English", LANG_JA: "日本語"}
_LANG_FILE = ".cmd_lang"


class CommandManager:
    def __init__(
        self,
        scheduler: TaskScheduler,
        recall: RecallManager,
        context_manager: ContextManager | None = None,
        webui: object | None = None,
        webui_error: str | None = None,
        persona_repo: PersonaRepository | None = None,
        event_repo: EventRepository | None = None,
        data_dir: Path | None = None,
        initial_lang: str = LANG_ZH,
    ) -> None:
        self._scheduler = scheduler
        self._recall = recall
        self._ctx = context_manager
        self._webui = webui
        self._webui_error = webui_error
        self._persona_repo = persona_repo
        self._event_repo = event_repo
        self._data_dir = data_dir
        # session_id → (confirm_key, expire_timestamp)
        self._pending: dict[str, tuple[str, float]] = {}
        # Language: try reading persisted preference, fall back to initial_lang
        self._lang = self._load_lang(initial_lang)

    # ------------------------------------------------------------------
    # i18n helpers
    # ------------------------------------------------------------------

    def _load_lang(self, default: str) -> str:
        if self._data_dir:
            lang_file = self._data_dir / _LANG_FILE
            if lang_file.exists():
                try:
                    saved = lang_file.read_text(encoding="utf-8").strip()
                    if saved in (LANG_ZH, LANG_EN, LANG_JA):
                        return saved
                except Exception:
                    pass
        return default

    def _save_lang(self) -> None:
        if self._data_dir:
            try:
                (self._data_dir / _LANG_FILE).write_text(self._lang, encoding="utf-8")
            except Exception as exc:
                logger.warning("[CommandManager] failed to save lang: %s", exc)

    def _t(self, key: str, **kwargs) -> str:
        s = get_string(key, self._lang)
        return s.format(**kwargs) if kwargs else s

    def _dim_names(self) -> dict[str, str]:
        return _DIM_NAMES.get(self._lang, _DIM_NAMES[LANG_ZH])

    # ------------------------------------------------------------------
    # Info commands
    # ------------------------------------------------------------------

    async def status(self) -> str:
        tasks = self._scheduler.task_names
        tasks_str = ", ".join(tasks) if tasks else self._t("cmd.status.tasks_none")
        sessions = self._ctx.active_sessions_count if self._ctx else "N/A"
        webui_s = self._t("cmd.status.webui_running") if (
            self._webui and getattr(self._webui, "_runner", None)
        ) else self._t("cmd.status.webui_stopped")
        return "\n".join([
            self._t("cmd.status.header"),
            self._t("cmd.status.tasks", tasks=tasks_str),
            self._t("cmd.status.sessions", count=sessions),
            self._t("cmd.status.webui", status=webui_s),
        ])

    async def persona(self, platform: str, physical_id: str) -> str:
        if self._persona_repo is None:
            return self._t("cmd.persona.no_repo")
        p = await self._persona_repo.get_by_identity(platform, physical_id)
        if p is None:
            return self._t("cmd.persona.not_found", platform=platform, id=physical_id)

        lines = [self._t("cmd.persona.header", name=p.primary_name, id=physical_id)]
        attrs = p.persona_attrs
        desc = attrs.get("description", "")
        if desc:
            lines.append(self._t("cmd.persona.description", desc=desc))

        bf: dict = attrs.get("big_five", {})
        if bf:
            lines.append(self._t("cmd.persona.bigfive_header"))
            evidence: dict | str = attrs.get("big_five_evidence", {})
            dim_names = self._dim_names()
            for dim in ["O", "C", "E", "A", "N"]:
                val = bf.get(dim)
                if val is None:
                    continue
                pct = round((float(val) + 1.0) / 2.0 * 100)
                label = dim_names.get(dim, dim)
                ev = evidence.get(dim, "") if isinstance(evidence, dict) else ""
                if ev:
                    lines.append(self._t("cmd.persona.bigfive_dim_ev", label=label, pct=pct, ev=ev[:60]))
                else:
                    lines.append(self._t("cmd.persona.bigfive_dim", label=label, pct=pct))

        tags = attrs.get("tags", [])
        if tags:
            lines.append(self._t("cmd.persona.tags", tags=", ".join(tags)))
        lines.append(self._t("cmd.persona.confidence", pct=round(p.confidence * 100)))
        return "\n".join(lines)

    async def soul(self, session_id: str, soul_states: dict) -> str:
        state = soul_states.get(session_id)
        if state is None:
            return self._t("cmd.soul.neutral")

        def _fmt(val: float) -> str:
            if abs(val) < 1.0:
                return f"{val:+.1f}/20（{self._t('cmd.soul.level_neutral')}）"
            level = self._t("cmd.soul.level_high") if val > 0 else self._t("cmd.soul.level_low")
            return f"{val:+.1f}/20（{level}）"

        return "\n".join([
            self._t("cmd.soul.header"),
            self._t("cmd.soul.recall_depth", val=_fmt(state.recall_depth)),
            self._t("cmd.soul.impression_depth", val=_fmt(state.impression_depth)),
            self._t("cmd.soul.expression_desire", val=_fmt(state.expression_desire)),
            self._t("cmd.soul.creativity", val=_fmt(state.creativity)),
        ])

    async def recall(self, query: str, group_id: str | None = None) -> str:
        results = await self._recall.recall(query, group_id=group_id)
        if not results:
            return self._t("cmd.recall.not_found", query=query)
        return format_events_for_prompt(results, token_budget=800)

    # ------------------------------------------------------------------
    # Action commands
    # ------------------------------------------------------------------

    async def run_task(self, task: str) -> str:
        ok = await self._scheduler.run_now(task.strip())
        if ok:
            return self._t("cmd.task.triggered", task=task)
        available = ", ".join(self._scheduler.task_names) or self._t("cmd.status.tasks_none")
        return self._t("cmd.task.not_found", task=task, available=available)

    async def flush(self, session_id: str) -> str:
        if self._ctx is None:
            return self._t("cmd.flush.no_ctx")
        window = self._ctx.pop_window(session_id)
        if window is None:
            return self._t("cmd.flush.no_window")
        count = len(window.messages) if hasattr(window, "messages") else "?"
        return self._t("cmd.flush.done", count=count)

    async def webui(self, action: str) -> str:
        action = action.strip().lower()
        if self._webui is None:
            if self._webui_error:
                return self._t("cmd.webui.start_failed", error=self._webui_error)
            return self._t("cmd.webui.not_loaded")
        if action == "on":
            try:
                await self._webui.start()
                host = getattr(self._webui, "_host", "localhost")
                port = getattr(self._webui, "_port", "?")
                return self._t("cmd.webui.started", host=host, port=port)
            except Exception as e:
                return self._t("cmd.webui.start_failed", error=e)
        elif action == "off":
            try:
                await self._webui.stop()
                return self._t("cmd.webui.stopped")
            except Exception as e:
                return self._t("cmd.webui.stop_failed", error=e)
        return self._t("cmd.webui.usage")

    async def set_language(self, code: str) -> str:
        lang = _LANG_ALIASES.get(code.lower().strip())
        if lang is None:
            return self._t("cmd.lang.invalid")
        self._lang = lang
        self._save_lang()
        return self._t("cmd.lang.set", lang=_LANG_DISPLAY[lang])

    # ------------------------------------------------------------------
    # Reset commands (all require two-step confirmation)
    # ------------------------------------------------------------------

    async def _confirm(
        self,
        session_id: str,
        key: str,
        action: Callable[[], Awaitable[str]],
        description: str,
    ) -> str:
        pending = self._pending.get(session_id)
        if pending and pending[0] == key and time.time() < pending[1]:
            del self._pending[session_id]
            return await action()
        self._pending[session_id] = (key, time.time() + _CONFIRM_TTL)
        return self._t("cmd.reset.confirm_warn", desc=description, ttl=int(_CONFIRM_TTL))

    async def reset_here(self, session_id: str, group_id: str | None) -> str:
        if self._event_repo is None:
            return self._t("cmd.reset.no_event_repo")

        async def _do() -> str:
            count = await self._event_repo.delete_by_group(group_id)
            deleted_summaries = 0
            if group_id and self._data_dir:
                summary_dir = self._data_dir / "groups" / group_id / "summaries"
                if summary_dir.exists():
                    for f in summary_dir.glob("*.md"):
                        f.unlink()
                        deleted_summaries += 1
            base = self._t("cmd.reset.here_done", count=count)
            if deleted_summaries:
                base += "，" + self._t("cmd.reset.summary_suffix", count=deleted_summaries)
            return base + "。"

        scope_key = "cmd.reset.scope_group" if group_id else "cmd.reset.scope_private"
        scope = self._t(scope_key, gid=group_id or "")
        desc = self._t("cmd.reset.desc_here", scope=scope)
        return await self._confirm(session_id, f"reset_here_{group_id}", _do, desc)

    async def reset_event_by_group(self, session_id: str, group_id: str) -> str:
        if self._event_repo is None:
            return self._t("cmd.reset.no_event_repo")

        async def _do() -> str:
            count = await self._event_repo.delete_by_group(group_id)
            deleted_summaries = 0
            if self._data_dir:
                summary_dir = self._data_dir / "groups" / group_id / "summaries"
                if summary_dir.exists():
                    for f in summary_dir.glob("*.md"):
                        f.unlink()
                        deleted_summaries += 1
            base = self._t("cmd.reset.event_group_done", gid=group_id, count=count)
            if deleted_summaries:
                base += "，" + self._t("cmd.reset.summary_suffix", count=deleted_summaries)
            return base + "。"

        desc = self._t("cmd.reset.desc_event_group", gid=group_id)
        return await self._confirm(session_id, f"reset_event_{group_id}", _do, desc)

    async def reset_event_all(self, session_id: str) -> str:
        if self._event_repo is None:
            return self._t("cmd.reset.no_event_repo")

        async def _do() -> str:
            count = await self._event_repo.delete_all()
            return self._t("cmd.reset.event_all_done", count=count)

        return await self._confirm(
            session_id, "reset_event_all", _do,
            self._t("cmd.reset.desc_event_all")
        )

    async def reset_persona_one(self, session_id: str, platform: str, physical_id: str) -> str:
        if self._persona_repo is None:
            return self._t("cmd.reset.no_persona_repo")

        async def _do() -> str:
            p = await self._persona_repo.get_by_identity(platform, physical_id)
            if p is None:
                return self._t("cmd.reset.persona_not_found", platform=platform, id=physical_id)
            await self._persona_repo.delete(p.uid)
            return self._t("cmd.reset.persona_one_done", name=p.primary_name, id=physical_id)

        desc = self._t("cmd.reset.desc_persona_one", id=physical_id)
        return await self._confirm(session_id, f"reset_persona_{physical_id}", _do, desc)

    async def reset_persona_all(self, session_id: str) -> str:
        if self._persona_repo is None:
            return self._t("cmd.reset.no_persona_repo")

        async def _do() -> str:
            all_p = await self._persona_repo.list_all()
            for p in all_p:
                await self._persona_repo.delete(p.uid)
            return self._t("cmd.reset.persona_all_done", count=len(all_p))

        return await self._confirm(
            session_id, "reset_persona_all", _do,
            self._t("cmd.reset.desc_persona_all")
        )

    async def reset_all(self, session_id: str) -> str:
        if self._event_repo is None or self._persona_repo is None:
            return self._t("cmd.reset.no_repo")

        async def _do() -> str:
            import shutil
            ev_count = await self._event_repo.delete_all()
            all_p = await self._persona_repo.list_all()
            for p in all_p:
                await self._persona_repo.delete(p.uid)
            if self._data_dir:
                for folder in ("groups", "personas"):
                    target = self._data_dir / folder
                    if target.exists():
                        shutil.rmtree(target)
            return self._t("cmd.reset.all_done", ev_count=ev_count, p_count=len(all_p))

        return await self._confirm(
            session_id, "reset_all", _do,
            self._t("cmd.reset.desc_all")
        )

    # ------------------------------------------------------------------
    # Help
    # ------------------------------------------------------------------

    async def help(self) -> str:
        return self._t("cmd.help.full")
