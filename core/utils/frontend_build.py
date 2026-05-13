"""Utility for building the Next.js frontend and copying output to pages/moirai/.

The build command is `npm run build` (defined in web/frontend/package.json as
`next build && node scripts/copy-export.mjs`).  copy-export.mjs handles moving
the `out/` directory to `pages/moirai/` automatically, so this module only needs
to invoke npm.
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
_PAGES_INDEX = _REPO_ROOT / "pages" / "moirai" / "index.html"

# Conda env where Node.js lives on the developer's machine (CLAUDE.md convention).
_CONDA_NODE_BIN = Path.home() / "miniconda3" / "envs" / "node" / "bin"


def _find_npm() -> str | None:
    """Return the path to npm, checking PATH then the known conda env."""
    if shutil.which("npm"):
        return "npm"
    candidate = _CONDA_NODE_BIN / "npm"
    if candidate.exists():
        return str(candidate)
    return None


def build_frontend(force: bool = False) -> bool:
    """Build the Next.js frontend and copy output to pages/moirai/.

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
    # Ensure conda node bin is on PATH so npm can find node
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

    if not _PAGES_INDEX.exists():
        logger.error(
            "[FrontendBuild] Build finished but pages/moirai/index.html not found. "
            "Check copy-export.mjs output above."
        )
        return False

    logger.info("[FrontendBuild] Frontend built successfully → %s", _PAGES_INDEX.parent)
    return True
