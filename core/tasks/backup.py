"""Periodic database backup and retention management."""
from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)


async def run_database_backup(db_path: Path, backup_dir: Path, retention_days: int) -> bool:
    """Copy the database to the backup directory and prune old backups."""
    if not db_path.exists():
        logger.warning("[BackupTask] Source database not found at %s", db_path)
        return False

    backup_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Create new backup
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"core_{timestamp}.db"
    
    try:
        # Use copy2 to preserve metadata. For SQLite, we assume WAL mode is handling
        # consistency, or this is called when DB is idle.
        shutil.copy2(db_path, backup_path)
        # Also copy WAL and SHM if they exist
        for suffix in (".db-wal", ".db-shm"):
            sidecar = db_path.with_suffix(suffix)
            if sidecar.exists():
                shutil.copy2(sidecar, backup_path.with_suffix(suffix))
        
        logger.info("[BackupTask] Database backed up to %s", backup_path.name)
    except Exception as exc:
        logger.error("[BackupTask] Failed to create backup: %s", exc)
        return False

    # 2. Prune old backups
    try:
        cutoff = time.time() - (retention_days * 86400)
        pruned_count = 0
        for f in backup_dir.glob("core_*.db*"):
            if f.stat().st_mtime < cutoff:
                f.unlink()
                pruned_count += 1
        if pruned_count > 0:
            logger.info("[BackupTask] Pruned %d old backups (retention=%d days)", pruned_count, retention_days)
    except Exception as exc:
        logger.warning("[BackupTask] Failed to prune old backups: %s", exc)

    return True
