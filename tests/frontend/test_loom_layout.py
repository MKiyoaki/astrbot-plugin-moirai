"""Frontend structural tests for The Loom layout upgrade.

These tests verify that the relevant source files contain the expected
component structure without running a browser — fast, zero-dependency
checks that can run in CI alongside the Python test suite.

Coverage:
- page-header.tsx  supports loom variant
- app-shell.tsx    has MobileTabBar with data-testid
- source-panel.tsx exists and exports SourcePanel + buildThreads
- detail-panel.tsx exists and exports DetailPanel
- events/page.tsx  uses new layout landmarks and no longer imports FilterBar
- event-timeline.tsx  accepts externalDimmedIds prop
"""
from __future__ import annotations

import re
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

FRONTEND = (
    Path(__file__).parent.parent.parent          # repo root
    / "web" / "frontend"
)

# Resolve via the plugin data path if the relative path doesn't exist
if not FRONTEND.exists():
    _alt = Path.home() / (
        "Documents/Projects/Personal/astrbot/data/plugins"
        "/astrbot_plugin_moirai/web/frontend"
    )
    if _alt.exists():
        FRONTEND = _alt


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


# ── page-header.tsx ───────────────────────────────────────────────────────────

class TestPageHeaderLoomVariant:
    def test_variant_prop_declared(self):
        src = _read("components/layout/page-header.tsx")
        assert "variant?: 'default' | 'loom'" in src, (
            "PageHeader must declare variant prop with 'loom' option"
        )

    def test_loom_branch_renders_title(self):
        src = _read("components/layout/page-header.tsx")
        # The loom branch must render the title h1
        loom_block_start = src.find("if (variant === 'loom')")
        assert loom_block_start != -1, "Loom variant branch missing"
        loom_block = src[loom_block_start:loom_block_start + 1500]
        assert "<h1" in loom_block, "Loom header must render an h1"

    def test_loom_legend_prop(self):
        src = _read("components/layout/page-header.tsx")
        assert "loomLegend" in src, "PageHeader must accept loomLegend prop"

    def test_loom_window_prop(self):
        src = _read("components/layout/page-header.tsx")
        assert "loomWindow" in src, "PageHeader must accept loomWindow prop"


# ── app-shell.tsx ─────────────────────────────────────────────────────────────

class TestAppShellMobileTabBar:
    def test_mobile_tab_bar_component_exists(self):
        src = _read("components/layout/app-shell.tsx")
        assert "MobileTabBar" in src, "AppShell must define MobileTabBar"

    def test_mobile_tab_bar_testid(self):
        src = _read("components/layout/app-shell.tsx")
        assert 'data-testid="mobile-tab-bar"' in src, (
            "MobileTabBar nav must have data-testid='mobile-tab-bar' for tests"
        )

    def test_mobile_tab_bar_hidden_on_md(self):
        src = _read("components/layout/app-shell.tsx")
        # The tab bar should only appear below md breakpoint
        assert "md:hidden" in src, (
            "MobileTabBar must use md:hidden so it disappears on desktop"
        )

    def test_events_tab_present(self):
        src = _read("components/layout/app-shell.tsx")
        assert "/events" in src, "MobileTabBar must include /events tab"

    def test_recall_tab_present(self):
        src = _read("components/layout/app-shell.tsx")
        assert "/recall" in src, "MobileTabBar must include /recall tab"

    def test_settings_tab_present(self):
        src = _read("components/layout/app-shell.tsx")
        assert "/settings" in src, "MobileTabBar must include /settings tab"

    def test_sidebar_hidden_on_mobile(self):
        src = _read("components/layout/app-shell.tsx")
        # Sidebar should be wrapped in a hidden md:contents div
        assert "hidden md:contents" in src, (
            "AppSidebar must be hidden on mobile (hidden md:contents)"
        )


# ── source-panel.tsx ──────────────────────────────────────────────────────────

class TestSourcePanel:
    def test_file_exists(self):
        assert (FRONTEND / "components/events/source-panel.tsx").exists()

    def test_exports_source_panel(self):
        src = _read("components/events/source-panel.tsx")
        assert "export function SourcePanel" in src

    def test_exports_build_threads(self):
        src = _read("components/events/source-panel.tsx")
        assert "export function buildThreads" in src

    def test_source_panel_testid(self):
        src = _read("components/events/source-panel.tsx")
        assert 'data-testid="source-panel"' in src

    def test_hidden_on_mobile(self):
        src = _read("components/events/source-panel.tsx")
        assert "hidden md:flex" in src, (
            "SourcePanel must be hidden on mobile (hidden md:flex)"
        )

    def test_toggle_handler(self):
        src = _read("components/events/source-panel.tsx")
        assert "onToggle" in src, "SourcePanel must accept onToggle callback"

    def test_dimmed_ids_prop(self):
        src = _read("components/events/source-panel.tsx")
        assert "dimmedIds" in src, "SourcePanel must accept dimmedIds prop"

    def test_colored_strip_rendered(self):
        src = _read("components/events/source-panel.tsx")
        # The colour strip uses th.color inline style
        assert "th.color" in src, "SourcePanel must render per-source colour"


# ── detail-panel.tsx ──────────────────────────────────────────────────────────

class TestDetailPanel:
    def test_file_exists(self):
        assert (FRONTEND / "components/events/detail-panel.tsx").exists()

    def test_exports_detail_panel(self):
        src = _read("components/events/detail-panel.tsx")
        assert "export function DetailPanel" in src

    def test_testid_on_desktop_aside(self):
        src = _read("components/events/detail-panel.tsx")
        assert 'data-testid="detail-panel"' in src

    def test_falls_back_to_sheet_on_mobile(self):
        src = _read("components/events/detail-panel.tsx")
        assert "Sheet" in src and "useIsMobile" in src, (
            "DetailPanel must use Sheet on mobile via useIsMobile"
        )

    def test_width_transition(self):
        src = _read("components/events/detail-panel.tsx")
        # Desktop panel keeps an explicit responsive width and animates layout changes.
        assert "transition-all" in src and "w-[360px]" in src and "xl:w-[440px]" in src, (
            "DetailPanel desktop aside must define responsive width classes with a transition"
        )

    def test_close_button(self):
        src = _read("components/events/detail-panel.tsx")
        assert "onClose" in src, "DetailPanel must expose onClose handler"


# ── events/page.tsx ───────────────────────────────────────────────────────────

class TestEventsPageLayout:
    def test_uses_filter_bar(self):
        src = _read("app/events/page.tsx")
        assert "FilterBar" in src, (
            "events/page.tsx should keep FilterBar for tag/date filtering"
        )

    def test_does_not_use_source_panel(self):
        src = _read("app/events/page.tsx")
        assert "SourcePanel" not in src

    def test_uses_detail_panel(self):
        src = _read("app/events/page.tsx")
        assert "DetailPanel" in src, "events/page.tsx must use DetailPanel"

    def test_loom_layout_testid(self):
        src = _read("app/events/page.tsx")
        assert 'data-testid="loom-layout"' in src, (
            "events/page.tsx three-column wrapper must have data-testid='loom-layout'"
        )

    def test_loom_header_variant(self):
        src = _read("app/events/page.tsx")
        assert "variant=\"loom\"" in src or "variant='loom'" in src, (
            "events/page.tsx must pass variant='loom' to PageHeader"
        )

    def test_build_threads_imported(self):
        src = _read("app/events/page.tsx")
        assert "buildThreads" not in src

    def test_uses_spindle_grid_and_event_thread(self):
        src = _read("app/events/page.tsx")
        assert "SpindleGrid" in src, "events/page.tsx must render the spindle grid"
        assert "EventThread" in src, "events/page.tsx must render the expanded thread view"
        assert "EventTimeline" not in src, (
            "events/page.tsx should no longer import/render the old multi-column timeline"
        )

    def test_uses_spindle_aggregation(self):
        src = _read("app/events/page.tsx")
        assert "buildSpindleCards" in src
        assert "eventGroupId" in src
        assert "expandedGroupId" in src

    def test_focus_event_expands_group(self):
        src = _read("app/events/page.tsx")
        assert "em_focus_event" in src
        assert "em_highlight_events" in src
        assert "setExpandedGroupId(eventGroupId(ev))" in src

    def test_back_to_spindles_action(self):
        src = _read("app/events/page.tsx")
        assert "backToSpindles" in src
        assert "setExpandedGroupId(null)" in src

    def test_no_sheet_directly(self):
        """Detail Sheet is now managed by DetailPanel, not inline in events/page."""
        src = _read("app/events/page.tsx")
        # Sheet import should not appear; DetailPanel encapsulates it
        assert "SheetContent" not in src, (
            "events/page.tsx must not import SheetContent directly — use DetailPanel"
        )


# ── New Event Stream reconfiguration components ───────────────────────────────

class TestEventStreamReconfigurationFiles:
    def test_aggregator_exists(self):
        src = _read("lib/events-aggregator.ts")
        assert "export function buildSpindleCards" in src
        assert "export interface SpindleCard" in src
        assert "groupAccent" in src

    def test_session_clustering_exists(self):
        src = _read("lib/session-clustering.ts")
        assert "export function buildSessions" in src
        assert "export interface EventSession" in src

    def test_spindle_grid_exists(self):
        src = _read("components/events/spindle-grid.tsx")
        assert "export function SpindleGrid" in src
        assert "spindles:" in src
        assert "onOpen" in src

    def test_spindle_card_uses_mini_thread(self):
        src = _read("components/events/spindle-card.tsx")
        assert "export function SpindleCard" in src
        assert "MiniThread" in src
        assert "unspool" in src

    def test_mini_thread_renders_svg_knots(self):
        src = _read("components/events/mini-thread.tsx")
        assert "export function MiniThread" in src
        assert "silk-flow" in src
        assert "status === 'archived'" in src

    def test_event_thread_filters_by_page_input(self):
        src = _read("components/events/event-thread.tsx")
        assert "export function EventThread" in src
        assert "buildSessions" in src
        assert "foreignObject" in src
        assert "onSelectionChange(null)" in src


# ── event-timeline.tsx ────────────────────────────────────────────────────────

class TestEventTimelineExternalDimming:
    def test_external_dimmed_ids_prop(self):
        src = _read("components/events/event-timeline.tsx")
        assert "externalDimmedIds" in src, (
            "EventTimeline must accept externalDimmedIds prop for SourcePanel integration"
        )

    def test_falls_back_to_internal(self):
        src = _read("components/events/event-timeline.tsx")
        assert "internalDimmedIds" in src, (
            "EventTimeline must keep internal dimming state as fallback"
        )

    def test_inline_toggle_hidden_when_external(self):
        src = _read("components/events/event-timeline.tsx")
        assert "!externalDimmedIds" in src, (
            "Inline ToggleGroup must be hidden when externalDimmedIds is provided"
        )
