import pytest
import shutil
import time
from pathlib import Path
from core.tasks.backup import run_database_backup

@pytest.mark.asyncio
async def test_run_database_backup(tmp_path):
    db_path = tmp_path / "core.db"
    db_path.write_text("fake db content")
    
    backup_dir = tmp_path / "backups"
    
    # 1. Test successful backup
    success = await run_database_backup(db_path, backup_dir, retention_days=7)
    assert success is True
    assert backup_dir.exists()
    backups = list(backup_dir.glob("core_*.db"))
    assert len(backups) == 1
    assert backups[0].read_text() == "fake db content"

@pytest.mark.asyncio
async def test_run_database_backup_no_source(tmp_path):
    db_path = tmp_path / "nonexistent.db"
    backup_dir = tmp_path / "backups"
    
    success = await run_database_backup(db_path, backup_dir, retention_days=7)
    assert success is False

@pytest.mark.asyncio
async def test_run_database_backup_pruning(tmp_path):
    db_path = tmp_path / "core.db"
    db_path.write_text("content")
    
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    
    # Create an old backup file
    old_backup = backup_dir / "core_20200101_000000.db"
    old_backup.write_text("old content")
    
    # Set mtime to way back
    old_mtime = time.time() - (10 * 86400) # 10 days ago
    import os
    os.utime(old_backup, (old_mtime, old_mtime))
    
    # Run backup with 7 days retention
    success = await run_database_backup(db_path, backup_dir, retention_days=7)
    assert success is True
    
    assert not old_backup.exists()
    assert len(list(backup_dir.glob("core_*.db"))) == 1 # only the new one
