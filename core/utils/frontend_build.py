"""Utility for building the Next.js frontend.

`npm run build` outputs a static export to web/frontend/out/.
The output is copied verbatim to pages/moirai/ — no path rewriting needed.
"""
from __future__ import annotations

import logging
import os
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

def _find_npm() -> str | None:
    if shutil.which("npm"):
        return "npm"
    candidate = _CONDA_NODE_BIN / "npm"
    if candidate.exists():
        return str(candidate)
    return None


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

    if _PAGES_DIR.exists():
        shutil.rmtree(_PAGES_DIR)
    shutil.copytree(_OUT_DIR, _PAGES_DIR)

    logger.info("[FrontendBuild] Frontend built successfully → %s", _PAGES_DIR)
    return True
