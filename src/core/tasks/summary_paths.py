"""Filesystem layout for daily narrative summaries.

Single source of truth for where a summary file lives.  A summary is keyed by
three independent dimensions and every one of them is part of the path:

    data_dir/groups/<gid>/summaries/<persona>/<YYYY-MM-DD>.md
    data_dir/private/<peer_uid>/summaries/<persona>/<YYYY-MM-DD>.md
    data_dir/global/summaries/<persona>/<YYYY-MM-DD>.md   (legacy merged private)

``<persona>`` is ``__default__`` for events whose ``bot_persona_name`` is NULL.
The legacy layout (flat ``summaries/<YYYY-MM-DD>.md``) is migrated into
``__default__/`` on startup and still recognised by ``iter_summary_files``.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator

logger = logging.getLogger(__name__)

PERSONA_DIR_DEFAULT = "__default__"

KIND_GROUP = "group"
KIND_PRIVATE = "private"
KIND_LEGACY_PRIVATE = "legacy_private"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_UNSAFE_RE = re.compile(r'[\x00-\x1f\x7f/\\:*?"<>|]')
_PERSONA_DIR_MAX = 64


def persona_dirname(name: str | None) -> str:
    """Map a bot persona name to a filesystem-safe directory name.

    Sanitisation is one-way; use ``resolve_persona_dirname`` to go back.  A hash
    suffix is appended whenever sanitisation changed the string so that two
    distinct persona names can never collapse onto the same directory.
    """
    if name is None or name == "":
        return PERSONA_DIR_DEFAULT

    cleaned = _UNSAFE_RE.sub("_", name).strip(" .")
    truncated = cleaned[:_PERSONA_DIR_MAX]
    if truncated and truncated == name and truncated != PERSONA_DIR_DEFAULT:
        return truncated

    digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
    stem = truncated or "persona"
    return f"{stem}-{digest}"


def resolve_persona_dirname(
    dirname: str, known_names: Iterable[str | None],
) -> str | None:
    """Reverse ``persona_dirname`` against the persona names present in the DB.

    Returns None for the default bucket.  An unrecognised directory yields the
    directory name itself so orphaned data stays visible in the WebUI.
    """
    if dirname == PERSONA_DIR_DEFAULT:
        return None
    for candidate in known_names:
        if candidate and persona_dirname(candidate) == dirname:
            return candidate
    return dirname


@dataclass(frozen=True)
class SummaryRef:
    """One summary file, fully identified by its three scope dimensions."""

    kind: str
    group_id: str | None
    peer_uid: str | None
    persona_dir: str
    date: str
    path: Path


def summary_dir_from_dirname(
    data_dir: Path,
    *,
    persona_dir: str,
    group_id: str | None = None,
    peer_uid: str | None = None,
) -> Path:
    """Return a scope directory addressed by an already-computed persona dir."""
    safe = _UNSAFE_RE.sub("_", persona_dir).strip(" .") or PERSONA_DIR_DEFAULT
    if group_id is not None:
        return data_dir / "groups" / group_id / "summaries" / safe
    if peer_uid is not None:
        return data_dir / "private" / peer_uid / "summaries" / safe
    return data_dir / "global" / "summaries" / safe


def summary_dir(
    data_dir: Path,
    *,
    group_id: str | None = None,
    peer_uid: str | None = None,
    persona: str | None = None,
) -> Path:
    """Return the directory holding one scope's summaries."""
    return summary_dir_from_dirname(
        data_dir, persona_dir=persona_dirname(persona),
        group_id=group_id, peer_uid=peer_uid,
    )


def summary_path(
    data_dir: Path,
    *,
    date: str,
    group_id: str | None = None,
    peer_uid: str | None = None,
    persona: str | None = None,
    persona_dir: str | None = None,
) -> Path:
    """Path of one summary file; persona_dir wins over persona when supplied."""
    base = (
        summary_dir_from_dirname(
            data_dir, persona_dir=persona_dir, group_id=group_id, peer_uid=peer_uid,
        )
        if persona_dir
        else summary_dir(
            data_dir, group_id=group_id, peer_uid=peer_uid, persona=persona,
        )
    )
    return base / f"{date}.md"


def _iter_scope_roots(data_dir: Path) -> Iterator[tuple[str, str | None, str | None, Path]]:
    groups_dir = data_dir / "groups"
    if groups_dir.is_dir():
        for gid_dir in sorted(groups_dir.iterdir()):
            if gid_dir.is_dir():
                yield KIND_GROUP, gid_dir.name, None, gid_dir / "summaries"

    private_dir = data_dir / "private"
    if private_dir.is_dir():
        for peer_dir in sorted(private_dir.iterdir()):
            if peer_dir.is_dir():
                yield KIND_PRIVATE, None, peer_dir.name, peer_dir / "summaries"

    global_dir = data_dir / "global" / "summaries"
    if global_dir.is_dir():
        yield KIND_LEGACY_PRIVATE, None, None, global_dir


def iter_summary_files(data_dir: Path) -> Iterator[SummaryRef]:
    """Walk every summary file, recognising both the new and legacy layouts."""
    for kind, group_id, peer_uid, root in _iter_scope_roots(data_dir):
        if not root.is_dir():
            continue
        for flat in sorted(root.glob("*.md"), reverse=True):
            if _DATE_RE.match(flat.stem):
                yield SummaryRef(
                    kind, group_id, peer_uid, PERSONA_DIR_DEFAULT, flat.stem, flat,
                )
        for persona_dir in sorted(root.iterdir()):
            if not persona_dir.is_dir():
                continue
            for f in sorted(persona_dir.glob("*.md"), reverse=True):
                if _DATE_RE.match(f.stem):
                    yield SummaryRef(
                        kind, group_id, peer_uid, persona_dir.name, f.stem, f,
                    )


def iter_summary_paths(data_dir: Path) -> Iterator[Path]:
    """Every summary file path, for callers that only need the files."""
    for ref in iter_summary_files(data_dir):
        yield ref.path


def scope_summary_paths(
    data_dir: Path,
    *,
    group_id: str | None = None,
    peer_uid: str | None = None,
) -> list[Path]:
    """Every summary file belonging to one group / private peer, all personas."""
    if group_id is not None:
        root = data_dir / "groups" / group_id / "summaries"
    elif peer_uid is not None:
        root = data_dir / "private" / peer_uid / "summaries"
    else:
        root = data_dir / "global" / "summaries"
    if not root.is_dir():
        return []
    return [p for p in sorted(root.glob("**/*.md")) if _DATE_RE.match(p.stem)]


def migrate_legacy_layout(data_dir: Path) -> int:
    """Move flat ``summaries/<date>.md`` files into ``summaries/__default__/``.

    Idempotent: files already inside a persona directory are untouched, and an
    existing destination is never overwritten.
    """
    moved = 0
    for _kind, _gid, _peer, root in _iter_scope_roots(data_dir):
        if not root.is_dir():
            continue
        flat = [p for p in root.glob("*.md") if _DATE_RE.match(p.stem)]
        if not flat:
            continue
        target_dir = root / PERSONA_DIR_DEFAULT
        target_dir.mkdir(parents=True, exist_ok=True)
        for src in flat:
            dst = target_dir / src.name
            if dst.exists():
                continue
            try:
                src.replace(dst)
                moved += 1
            except OSError as exc:
                logger.warning("[SummaryPaths] cannot migrate %s: %s", src, exc)
    if moved:
        logger.info("[SummaryPaths] migrated %d legacy summary file(s)", moved)
    return moved
