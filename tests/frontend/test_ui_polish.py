"""Frontend structural tests for UI polish changes (v0.12.9).

Covers:
- Theme switcher: Popover in sidebar, 3-option segmented control in settings,
  3-button group in login page
- PageEmptyOverlay: new component exists and is used in events/graph/summary
- Tooltip additions in node-detail, edge-detail, detail-panel
"""
from __future__ import annotations

from pathlib import Path

FRONTEND = Path(__file__).parent.parent.parent / "web" / "frontend"
if not FRONTEND.exists():
    _alt = Path.home() / (
        "Documents/Projects/Personal/astrbot/data/plugins"
        "/astrbot_plugin_moirai/web/frontend"
    )
    if _alt.exists():
        FRONTEND = _alt


def _read(rel: str) -> str:
    return (FRONTEND / rel).read_text(encoding="utf-8")


# ── Theme switcher ─────────────────────────────────────────────────────────────

class TestThemeSwitcherSidebar:
    def setup_method(self):
        self.src = _read("components/layout/app-sidebar.tsx")

    def test_imports_popover(self):
        assert "PopoverContent" in self.src

    def test_imports_monitor_icon(self):
        assert "Monitor" in self.src

    def test_imports_check_icon(self):
        assert "Check" in self.src

    def test_has_theme_popover_open_state(self):
        assert "themePopoverOpen" in self.src

    def test_has_three_theme_options(self):
        assert "'light'" in self.src
        assert "'dark'" in self.src
        assert "'system'" in self.src

    def test_popover_closes_on_select(self):
        assert "setThemePopoverOpen(false)" in self.src

    def test_uses_theme_not_resolvedtheme(self):
        # Should use `theme` (stored preference) not `resolvedTheme` for active check
        assert "theme === opt.value" in self.src or "theme ===" in self.src


class TestThemeSwitcherSettings:
    def setup_method(self):
        self.src = _read("app/settings/page.tsx")

    def test_imports_monitor_icon(self):
        assert "Monitor" in self.src

    def test_has_three_theme_options_array(self):
        assert "themeOptions" in self.src

    def test_has_system_option(self):
        assert "'system'" in self.src

    def test_uses_theme_not_isDark(self):
        assert "isDark" not in self.src

    def test_segmented_control_rendered(self):
        assert "themeOptions.map" in self.src

    def test_uses_theme_i18n_keys(self):
        assert "themeLight" in self.src
        assert "themeDark" in self.src
        assert "themeSystem" in self.src


class TestThemeSwitcherLogin:
    def setup_method(self):
        self.src = _read("components/shared/login-screen.tsx")

    def test_imports_monitor_icon(self):
        assert "Monitor" in self.src

    def test_has_system_option(self):
        assert "'system'" in self.src

    def test_uses_theme_not_isDark(self):
        assert "isDark" not in self.src

    def test_three_options_rendered(self):
        # All three values present in source
        assert "'light'" in self.src
        assert "'dark'" in self.src
        assert "'system'" in self.src


# ── PageEmptyOverlay ──────────────────────────────────────────────────────────

class TestPageEmptyOverlay:
    def setup_method(self):
        self.component = _read("components/shared/page-empty-overlay.tsx")

    def test_file_exists(self):
        assert len(self.component) > 0

    def test_exports_page_empty_overlay(self):
        assert "PageEmptyOverlay" in self.component

    def test_has_backdrop_blur(self):
        assert "backdrop-blur" in self.component

    def test_has_flex_centered_layout(self):
        assert "items-center" in self.component
        assert "justify-center" in self.component

    def test_accepts_icon_prop(self):
        assert "icon" in self.component or "Icon" in self.component

    def test_has_fade_in_animation(self):
        assert "fade-in" in self.component


class TestPageEmptyOverlayUsage:
    def test_events_page_uses_overlay(self):
        src = _read("app/events/page.tsx")
        assert "PageEmptyOverlay" in src

    def test_graph_page_uses_overlay(self):
        src = _read("app/graph/page.tsx")
        assert "PageEmptyOverlay" in src

    def test_summary_page_uses_overlay(self):
        src = _read("app/summary/page.tsx")
        assert "PageEmptyOverlay" in src

    def test_events_page_imports_overlay(self):
        src = _read("app/events/page.tsx")
        assert "page-empty-overlay" in src

    def test_graph_page_imports_overlay(self):
        src = _read("app/graph/page.tsx")
        assert "page-empty-overlay" in src

    def test_summary_page_imports_overlay(self):
        src = _read("app/summary/page.tsx")
        assert "page-empty-overlay" in src


# ── Tooltip additions ─────────────────────────────────────────────────────────

class TestTooltipAdditions:
    def test_node_detail_has_tooltip(self):
        src = _read("components/graph/node-detail.tsx")
        assert "TooltipTrigger" in src
        assert "TooltipContent" in src

    def test_edge_detail_has_tooltip(self):
        src = _read("components/graph/edge-detail.tsx")
        assert "TooltipTrigger" in src
        assert "TooltipContent" in src

    def test_detail_panel_has_close_tooltip(self):
        src = _read("components/events/detail-panel.tsx")
        assert "TooltipTrigger" in src
        assert "TooltipContent" in src

    def test_node_detail_edit_tooltip(self):
        src = _read("components/graph/node-detail.tsx")
        assert "i18n.common.edit" in src

    def test_node_detail_delete_tooltip(self):
        src = _read("components/graph/node-detail.tsx")
        assert "i18n.common.delete" in src

    def test_edge_detail_edit_delete_tooltips(self):
        src = _read("components/graph/edge-detail.tsx")
        assert "i18n.common.edit" in src
        assert "i18n.common.delete" in src

    def test_detail_panel_close_tooltip(self):
        src = _read("components/events/detail-panel.tsx")
        assert "i18n.common.close" in src


# ── i18n keys for theme ───────────────────────────────────────────────────────

class TestThemeI18nKeys:
    def setup_method(self):
        self.src = _read("lib/i18n.ts")

    def test_zh_has_theme_keys(self):
        assert "themeLight: '浅色'" in self.src
        assert "themeDark: '深色'" in self.src
        assert "themeSystem: '跟随系统'" in self.src

    def test_ja_has_theme_keys(self):
        assert "themeLight: 'ライト'" in self.src
        assert "themeDark: 'ダーク'" in self.src
        assert "themeSystem: 'システムに従う'" in self.src

    def test_en_has_theme_keys(self):
        assert "themeLight: 'Light'" in self.src
        assert "themeDark: 'Dark'" in self.src
        assert "themeSystem: 'System'" in self.src
