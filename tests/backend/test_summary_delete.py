"""Tests for DELETE /api/summary endpoint in plugin_routes."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from aiohttp import web

import web.plugin_routes as pr_module
from web.plugin_routes import PluginRoutes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_routes(tmp_path: Path) -> PluginRoutes:
    routes = PluginRoutes.__new__(PluginRoutes)
    routes._data_dir = tmp_path
    return routes


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _delete(routes: PluginRoutes, group_id: str | None, date: str) -> web.Response:
    req = MagicMock(spec=web.Request)

    def fake_query(request, key, default=""):
        if key == "group_id":
            return group_id or ""
        if key == "date":
            return date
        return default

    with patch.object(pr_module, "_query", side_effect=fake_query):
        return _run(routes._handle_delete_summary(req))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestDeleteSummaryMissingDate:
    def test_returns_400_when_no_date(self, tmp_path):
        routes = _make_routes(tmp_path)
        req = MagicMock(spec=web.Request)
        with patch.object(pr_module, "_query", return_value=""):
            resp = _run(routes._handle_delete_summary(req))
        assert resp.status_code == 400

    def test_400_with_empty_group_and_no_date(self, tmp_path):
        routes = _make_routes(tmp_path)
        # Passing a non-empty group_id but still no date should also 400
        resp = _delete(routes, "g1", "")
        assert resp.status_code == 400


class TestDeleteSummaryNotFound:
    def test_returns_404_when_file_missing(self, tmp_path):
        routes = _make_routes(tmp_path)
        resp = _delete(routes, None, "2026-01-01")
        assert resp.status_code == 404

    def test_returns_404_for_missing_group_summary(self, tmp_path):
        routes = _make_routes(tmp_path)
        resp = _delete(routes, "g1", "2026-01-01")
        assert resp.status_code == 404


class TestDeleteGlobalSummary:
    def test_deletes_file_and_returns_200(self, tmp_path):
        routes = _make_routes(tmp_path)
        path = tmp_path / "global" / "summaries" / "2026-01-01.md"
        path.parent.mkdir(parents=True)
        path.write_text("content", encoding="utf-8")

        resp = _delete(routes, None, "2026-01-01")

        assert resp.status_code == 200
        assert not path.exists()

    def test_second_delete_returns_404(self, tmp_path):
        routes = _make_routes(tmp_path)
        path = tmp_path / "global" / "summaries" / "2026-01-02.md"
        path.parent.mkdir(parents=True)
        path.write_text("content", encoding="utf-8")

        _delete(routes, None, "2026-01-02")
        resp = _delete(routes, None, "2026-01-02")
        assert resp.status_code == 404


class TestDeleteGroupSummary:
    def test_deletes_group_file(self, tmp_path):
        routes = _make_routes(tmp_path)
        path = tmp_path / "groups" / "g1" / "summaries" / "2026-03-15.md"
        path.parent.mkdir(parents=True)
        path.write_text("group content", encoding="utf-8")

        resp = _delete(routes, "g1", "2026-03-15")

        assert resp.status_code == 200
        assert not path.exists()

    def test_does_not_delete_sibling_file(self, tmp_path):
        routes = _make_routes(tmp_path)
        base = tmp_path / "groups" / "g1" / "summaries"
        base.mkdir(parents=True)
        (base / "2026-03-15.md").write_text("a", encoding="utf-8")
        (base / "2026-03-16.md").write_text("b", encoding="utf-8")

        _delete(routes, "g1", "2026-03-15")

        assert not (base / "2026-03-15.md").exists()
        assert (base / "2026-03-16.md").exists()

    def test_does_not_affect_other_group(self, tmp_path):
        routes = _make_routes(tmp_path)
        for g in ("g1", "g2"):
            p = tmp_path / "groups" / g / "summaries" / "2026-03-15.md"
            p.parent.mkdir(parents=True)
            p.write_text("x", encoding="utf-8")

        _delete(routes, "g1", "2026-03-15")

        assert not (tmp_path / "groups" / "g1" / "summaries" / "2026-03-15.md").exists()
        assert (tmp_path / "groups" / "g2" / "summaries" / "2026-03-15.md").exists()
