"""Frontend structural tests for Phase 3c — Persona Selector.

Verifies that all relevant source files contain the expected structure
for the bot-persona scope feature without running a browser.

Coverage:
- store.tsx              exposes currentPersonaName / scopeMode / firstLaunchDone state + actions
- api.ts                 exports withPersona, BotPersonaItem, listBots; events.list / graph.get accept persona
- i18n.ts                personaSelector section present in zh/en/ja
- persona-selector.tsx   component exists, uses Avatar + Popover + useApp
- first-launch-persona-picker.tsx  component exists, uses Dialog + firstLaunchDone
- app-shell.tsx          imports and renders FirstLaunchPersonaPicker
- app-sidebar.tsx        imports and renders PersonaSelector
- events/page.tsx        passes personaFilter to api.events.list
- graph/page.tsx         passes personaFilter to api.graph.get
- library/page.tsx       passes personaFilter to api.graph.get and api.events.list
- stats/page.tsx         passes personaFilter to api.events.list and api.graph.get
"""
from __future__ import annotations

from pathlib import Path

FRONTEND = (
    Path(__file__).parent.parent.parent
    / "web" / "frontend"
)

if not FRONTEND.exists():
    _alt = Path.home() / (
        "Documents/Projects/Personal/astrbot/data/plugins"
        "/astrbot_plugin_moirai/web/frontend"
    )
    if _alt.exists():
        FRONTEND = _alt


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


# ── store.tsx ────────────────────────────────────────────────────────────────

class TestStore:
    def test_current_persona_name_in_state(self):
        src = _read("lib/store.tsx")
        assert "currentPersonaName" in src

    def test_scope_mode_in_state(self):
        src = _read("lib/store.tsx")
        assert "scopeMode" in src

    def test_first_launch_done_in_state(self):
        src = _read("lib/store.tsx")
        assert "firstLaunchDone" in src

    def test_set_current_persona_action(self):
        src = _read("lib/store.tsx")
        assert "setCurrentPersona" in src

    def test_set_first_launch_done_action(self):
        src = _read("lib/store.tsx")
        assert "setFirstLaunchDone" in src

    def test_localstorage_keys_present(self):
        src = _read("lib/store.tsx")
        assert "em_current_persona_name" in src
        assert "em_persona_scope_mode" in src
        assert "em_first_launch_done" in src

    def test_persona_state_in_usememo_deps(self):
        src = _read("lib/store.tsx")
        # All three persona states must appear in the useMemo dependency array
        assert "currentPersonaName" in src
        assert "scopeMode" in src
        assert "firstLaunchDone" in src


# ── api.ts ───────────────────────────────────────────────────────────────────

class TestApi:
    def test_with_persona_helper_exported(self):
        src = _read("lib/api.ts")
        assert "export function withPersona" in src

    def test_bot_persona_item_interface(self):
        src = _read("lib/api.ts")
        assert "BotPersonaItem" in src

    def test_list_bots_endpoint(self):
        src = _read("lib/api.ts")
        assert "listBots" in src
        assert "/api/personas/bots" in src

    def test_events_list_accepts_persona(self):
        src = _read("lib/api.ts")
        assert "list: (limit = 500, persona?" in src

    def test_events_list_archived_accepts_persona(self):
        src = _read("lib/api.ts")
        assert "listArchived: (persona?" in src

    def test_graph_get_accepts_persona(self):
        src = _read("lib/api.ts")
        assert "get: (persona?" in src

    def test_legacy_persona_token_exported(self):
        src = _read("lib/api.ts")
        assert "LEGACY_PERSONA_TOKEN" in src

    def test_impression_delete_api_exists(self):
        src = _read("lib/api.ts")
        assert "deleteImpression" in src
        assert "deleteImpressionsByScope" in src


# ── i18n.ts ──────────────────────────────────────────────────────────────────

class TestI18n:
    def test_persona_selector_section_zh(self):
        src = _read("lib/i18n.ts")
        # Check keys appear in the zh object (before the ja/en blocks)
        assert "personaSelector:" in src
        assert "allPersonas:" in src
        assert "firstLaunchTitle:" in src
        assert "viewAll:" in src

    def test_persona_selector_zh_content(self):
        src = _read("lib/i18n.ts")
        assert "所有 Bot" in src

    def test_persona_selector_en_content(self):
        src = _read("lib/i18n.ts")
        assert "All Bots" in src

    def test_persona_selector_ja_content(self):
        src = _read("lib/i18n.ts")
        assert "全 Bot" in src

    def test_three_persona_selector_sections(self):
        src = _read("lib/i18n.ts")
        # Should appear exactly 3 times (once per language)
        assert src.count("personaSelector:") == 3


# ── persona-selector.tsx ─────────────────────────────────────────────────────

class TestPersonaSelector:
    def test_file_exists(self):
        assert (FRONTEND / "components/shared/persona-selector.tsx").exists()

    def test_exports_persona_selector(self):
        src = _read("components/shared/persona-selector.tsx")
        assert "export function PersonaSelector" in src

    def test_uses_avatar(self):
        src = _read("components/shared/persona-selector.tsx")
        assert "Avatar" in src
        assert "AvatarFallback" in src

    def test_uses_popover(self):
        src = _read("components/shared/persona-selector.tsx")
        assert "Popover" in src

    def test_uses_use_app(self):
        src = _read("components/shared/persona-selector.tsx")
        assert "useApp" in src

    def test_calls_set_current_persona(self):
        src = _read("components/shared/persona-selector.tsx")
        assert "setCurrentPersona" in src

    def test_calls_list_bots(self):
        src = _read("components/shared/persona-selector.tsx")
        assert "listBots" in src


# ── first-launch-persona-picker.tsx ─────────────────────────────────────────

class TestFirstLaunchPersonaPicker:
    def test_file_exists(self):
        assert (FRONTEND / "components/shared/first-launch-persona-picker.tsx").exists()

    def test_exports_component(self):
        src = _read("components/shared/first-launch-persona-picker.tsx")
        assert "export function FirstLaunchPersonaPicker" in src

    def test_uses_dialog(self):
        src = _read("components/shared/first-launch-persona-picker.tsx")
        assert "Dialog" in src

    def test_checks_first_launch_done(self):
        src = _read("components/shared/first-launch-persona-picker.tsx")
        assert "firstLaunchDone" in src

    def test_calls_set_first_launch_done(self):
        src = _read("components/shared/first-launch-persona-picker.tsx")
        assert "setFirstLaunchDone" in src

    def test_calls_set_current_persona(self):
        src = _read("components/shared/first-launch-persona-picker.tsx")
        assert "setCurrentPersona" in src


# ── app-shell.tsx ────────────────────────────────────────────────────────────

class TestAppShell:
    def test_imports_first_launch_picker(self):
        src = _read("components/layout/app-shell.tsx")
        assert "FirstLaunchPersonaPicker" in src

    def test_renders_first_launch_picker(self):
        src = _read("components/layout/app-shell.tsx")
        assert "<FirstLaunchPersonaPicker" in src


# ── app-sidebar.tsx ──────────────────────────────────────────────────────────

class TestAppSidebar:
    def test_imports_persona_selector(self):
        src = _read("components/layout/app-sidebar.tsx")
        assert "PersonaSelector" in src

    def test_renders_persona_selector_in_footer(self):
        src = _read("components/layout/app-sidebar.tsx")
        assert "<PersonaSelector" in src

    def test_persona_selector_in_sidebar_footer(self):
        src = _read("components/layout/app-sidebar.tsx")
        # PersonaSelector must appear inside SidebarFooter block
        footer_start = src.find("SidebarFooter")
        selector_pos = src.find("<PersonaSelector", footer_start)
        assert selector_pos != -1, "PersonaSelector must be inside SidebarFooter"


# ── pages ────────────────────────────────────────────────────────────────────

class TestEventsPage:
    def test_reads_persona_filter(self):
        src = _read("app/events/page.tsx")
        assert "personaFilter" in src

    def test_passes_persona_to_list(self):
        src = _read("app/events/page.tsx")
        assert "api.events.list(1000, personaFilter)" in src

    def test_passes_persona_to_list_archived(self):
        src = _read("app/events/page.tsx")
        assert "listArchived(personaFilter)" in src


class TestGraphPage:
    def test_reads_persona_filter(self):
        src = _read("app/graph/page.tsx")
        assert "personaFilter" in src

    def test_passes_persona_to_graph_get(self):
        src = _read("app/graph/page.tsx")
        assert "api.graph.get(personaFilter)" in src

    def test_persona_filter_in_usecallback_deps(self):
        src = _read("app/graph/page.tsx")
        assert "personaFilter" in src
        assert "scopeMode" in src

    def test_renders_persona_supernodes(self):
        src = _read("app/graph/page.tsx")
        assert "PersonaSupernodeGrid" in src
        assert "api.graph.listBots" in src

    def test_deletes_impression_with_persona_filter(self):
        src = _read("app/graph/page.tsx")
        assert "api.graph.deleteImpression" in src
        assert "personaFilter" in src

    def test_bulk_deletes_scope_impressions(self):
        src = _read("app/graph/page.tsx")
        assert "deleteImpressionsByScope" in src
        assert "GROUP_ID_PRIVATE" in src


class TestGraphParamsPanel:
    def test_clear_scope_button_exists(self):
        src = _read("components/graph/params-panel.tsx")
        assert "clearScopeImpressions" in src
        assert "onClearScope" in src


class TestLibraryPage:
    def test_reads_persona_filter(self):
        src = _read("app/library/page.tsx")
        assert "personaFilter" in src

    def test_passes_persona_to_graph_get(self):
        src = _read("app/library/page.tsx")
        assert "api.graph.get(personaFilter)" in src

    def test_passes_persona_to_events_list(self):
        src = _read("app/library/page.tsx")
        assert "api.events.list(1000, personaFilter)" in src


class TestStatsPage:
    def test_reads_persona_filter(self):
        src = _read("app/stats/page.tsx")
        assert "personaFilter" in src

    def test_passes_persona_to_events_list(self):
        src = _read("app/stats/page.tsx")
        assert "api.events.list(2000, personaFilter)" in src

    def test_passes_persona_to_graph_get(self):
        src = _read("app/stats/page.tsx")
        assert "api.graph.get(personaFilter)" in src

    def test_load_data_uses_usecallback(self):
        src = _read("app/stats/page.tsx")
        assert "useCallback" in src
