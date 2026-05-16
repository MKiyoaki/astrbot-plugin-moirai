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
        # Panel animates in/out with width transition
        assert "w-0" in src and "w-80" in src, (
            "DetailPanel desktop aside must transition width (w-0 ↔ w-80)"
        )

    def test_close_button(self):
        src = _read("components/events/detail-panel.tsx")
        assert "onClose" in src, "DetailPanel must expose onClose handler"


# ── events/page.tsx ───────────────────────────────────────────────────────────

class TestEventsPageLayout:
    def test_no_filter_bar_import(self):
        src = _read("app/events/page.tsx")
        assert "FilterBar" not in src, (
            "events/page.tsx must not import FilterBar (replaced by SourcePanel)"
        )

    def test_uses_source_panel(self):
        src = _read("app/events/page.tsx")
        assert "SourcePanel" in src, "events/page.tsx must use SourcePanel"

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
        assert "buildThreads" in src, (
            "events/page.tsx must import buildThreads from source-panel"
        )

    def test_loom_legend_rendered(self):
        src = _read("app/events/page.tsx")
        assert "LoomLegend" in src, (
            "events/page.tsx must render LoomLegend component in header"
        )

    def test_no_sheet_directly(self):
        """Detail Sheet is now managed by DetailPanel, not inline in events/page."""
        src = _read("app/events/page.tsx")
        # Sheet import should not appear; DetailPanel encapsulates it
        assert "SheetContent" not in src, (
            "events/page.tsx must not import SheetContent directly — use DetailPanel"
        )


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
