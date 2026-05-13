"""Utility for building the Next.js frontend.

`npm run build` outputs a static export to web/frontend/out/.
The self-hosted WebuiServer serves out/ directly at root /.

For AstrBot Plugin Pages, out/ is copied to pages/moirai/ with HTML-only
path rewriting: absolute /_next/ and route hrefs are converted to relative
paths so AstrBot can inject asset_token and route correctly.
JS/CSS files are never touched.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).parent.parent.parent
_FRONTEND_DIR = _REPO_ROOT / "web" / "frontend"
_OUT_DIR = _FRONTEND_DIR / "out"
_PAGES_DIR = _REPO_ROOT / "pages" / "moirai"
_PAGES_INDEX = _PAGES_DIR / "index.html"

_CONDA_NODE_BIN = Path.home() / "miniconda3" / "envs" / "node" / "bin"

_ROUTES = {
    'events', 'graph', 'summary', 'recall', 'stats', 'library', 'config', 'settings',
}


def _find_npm() -> str | None:
    if shutil.which("npm"):
        return "npm"
    candidate = _CONDA_NODE_BIN / "npm"
    if candidate.exists():
        return str(candidate)
    return None


def _relative_prefix(html_file: Path) -> str:
    """Return the relative path prefix from html_file's directory to pages/moirai/."""
    parts = html_file.relative_to(_PAGES_DIR).parent.parts
    depth = len(parts)
    return "../" * depth if depth else "./"


def _rewrite_html(file: Path) -> None:
    """Rewrite absolute asset/route paths to relative in HTML files only."""
    if file.suffix != ".html":
        return
    prefix = _relative_prefix(file)
    text = file.read_text(encoding="utf-8")

    # Asset paths: /_next/ and /favicon.ico
    text = re.sub(r'(href=|src=|srcSet=|"\s*:\s*")(\\?")/(_next/)', lambda m: f'{m.group(1)}{m.group(2)}{prefix}_next/', text)
    text = text.replace('"/_next/', f'"{prefix}_next/')
    text = text.replace("'/_next/", f"'{prefix}_next/")
    text = text.replace('\\u002F_next\\u002F', f'\\u002F{prefix}_next\\u002F'.replace('/', '\\u002F'))
    text = re.sub(r'(href=(?:\\?"|\'))/favicon\.ico', lambda m: f'{m.group(1)}{prefix}favicon.ico', text)

    # Route hrefs: /events, /graph, etc.
    for route in _ROUTES:
        text = re.sub(
            rf'(href=(?:\\?"|\'))/{route}(?:/)?(?:\\?"|\')' ,
            lambda m, r=route, p=prefix: m.group(0).replace(f'/{r}', f'{p}{r}/'),
            text,
        )
    # Root href
    text = re.sub(r'href=(?:\\?"|\')/(?:\\?"|\')', lambda m: m.group(0).replace('href=', f'href=').replace('/', f'{prefix}', 1), text)
    file.write_text(text, encoding="utf-8")


def build_frontend(force: bool = False) -> bool:
    """Build the Next.js frontend and sync output to pages/moirai/.

    Skips the build if pages/moirai/index.html already exists and force=False.
    Returns True on success, False on failure.
    """
    if not force and _PAGES_INDEX.exists():
        logger.debug("[FrontendBuild] pages/moirai/ already built, skipping.")
        return True

    if not _FRONTEND_DIR.exists():
        logger.error("[FrontendBuild] Frontend source not found at %s", _FRONTEND_DIR)
        return False

    npm = _find_npm()
    if npm is None:
        logger.error(
            "[FrontendBuild] npm not found. "
            "Install Node.js or activate the 'node' conda env and retry."
        )
        return False

    env = os.environ.copy()
    if str(_CONDA_NODE_BIN) not in env.get("PATH", ""):
        env["PATH"] = str(_CONDA_NODE_BIN) + os.pathsep + env.get("PATH", "")

    logger.info("[FrontendBuild] Building frontend (npm run build) …")
    try:
        result = subprocess.run(
            [npm, "run", "build"],
            cwd=_FRONTEND_DIR,
            env=env,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        logger.error("[FrontendBuild] npm run build failed to start: %s", exc)
        return False

    if result.returncode != 0:
        logger.error(
            "[FrontendBuild] npm run build failed (exit %d):\n%s\n%s",
            result.returncode,
            result.stdout[-2000:],
            result.stderr[-2000:],
        )
        return False

    if not _OUT_DIR.exists():
        logger.error("[FrontendBuild] Build finished but out/ not found.")
        return False

    # Copy out/ → pages/moirai/, then rewrite HTML only (not JS/CSS)
    if _PAGES_DIR.exists():
        shutil.rmtree(_PAGES_DIR)
    shutil.copytree(_OUT_DIR, _PAGES_DIR)

    for html_file in _PAGES_DIR.rglob("*.html"):
        _rewrite_html(html_file)

    logger.info("[FrontendBuild] Frontend built successfully → %s", _PAGES_DIR)
    return True
