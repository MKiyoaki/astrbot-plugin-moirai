"""Emergency synchronous reset for the realtime dev environment.

Run this if run_realtime_dev.py crashed and left a stale state.
Mirrors every mutation that run_realtime_dev._archive_step() performed:

  1. Deletes .dev_data/realtime_test.db (if present)
  2. Restores the most-recent .dev_data/archive/dataflow_test_*.db
     back to .dev_data/dataflow_test.db (original is usually still intact
     because _archive_step uses copy2, but restores from archive on crash)
  3. Removes any realtime-generated .dev_data/groups/ directory
  4. Restores the most-recent .dev_data/archive/groups_<ts>/ back to
     .dev_data/groups/ (the demo summary files from run_webui_dev.py)

Usage:
    python reset_realtime_dev.py
"""

import shutil
import sys
from pathlib import Path

_ROOT       = Path(__file__).parent
DEV_DATA    = _ROOT / ".dev_data"
REALTIME_DB = DEV_DATA / "realtime_test.db"
DATAFLOW_DB = DEV_DATA / "dataflow_test.db"
GROUPS_DIR  = DEV_DATA / "groups"
ARCHIVE_DIR = DEV_DATA / "archive"


def main() -> int:
    print("=" * 50)
    print("  REALTIME DEV RESET")
    print("=" * 50)

    # Step 1: Delete stale realtime DB
    if REALTIME_DB.exists():
        try:
            REALTIME_DB.unlink()
            print(f"[Reset] Deleted {REALTIME_DB.name}")
        except PermissionError:
            print(
                f"[Reset] WARNING: {REALTIME_DB.name} is locked by another process.\n"
                "        Close LMStudio / any Python process holding the DB and retry."
            )
        except Exception as e:
            print(f"[Reset] Error deleting {REALTIME_DB.name}: {e}")
    else:
        print(f"[Reset] {REALTIME_DB.name} not found — nothing to delete")

    if not ARCHIVE_DIR.exists():
        print("[Reset] No archive directory found — skipping remaining restore steps")
        print("[Reset] Done.")
        return 0

    # Step 2: Restore most-recent archived dataflow DB (by mtime)
    db_candidates = sorted(
        ARCHIVE_DIR.glob("dataflow_test_*.db"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not db_candidates:
        print("[Reset] No archived dataflow_test_*.db found — skipping DB restore")
    else:
        latest_db = db_candidates[0]
        try:
            shutil.copy2(latest_db, DATAFLOW_DB)
            print(f"[Reset] Restored {latest_db.name} → dataflow_test.db")
        except Exception as e:
            print(f"[Reset] Error restoring DB: {e}")
        
        if len(db_candidates) > 1:
            print(f"        ({len(db_candidates) - 1} older DB archive(s) will be cleaned up)")

    # Step 3: Remove realtime-generated groups/ (summary files from this session)
    if GROUPS_DIR.exists():
        try:
            shutil.rmtree(GROUPS_DIR)
            print("[Reset] Removed realtime-generated .dev_data/groups/")
        except Exception as e:
            print(f"[Reset] Warning: Could not remove {GROUPS_DIR}: {e}")

    # Step 4: Restore the original groups/ dir (moved by _archive_step at startup)
    grp_candidates = sorted(
        ARCHIVE_DIR.glob("groups_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not grp_candidates:
        print("[Reset] No archived groups_<ts>/ found — summary dir stays empty")
    elif GROUPS_DIR.exists():
        print(f"[Reset] WARNING: {GROUPS_DIR.name} still exists (Step 3 failed); skipping restore to avoid nesting.")
    else:
        latest_grp = grp_candidates[0]
        try:
            shutil.move(str(latest_grp), str(GROUPS_DIR))
            print(f"[Reset] Restored {latest_grp.name}/ → .dev_data/groups/")
        except Exception as e:
            print(f"[Reset] Error restoring groups: {e}")
        
        if len(grp_candidates) > 1:
            print(f"        ({len(grp_candidates) - 1} older group archive(s) will be cleaned up)")

    # Step 5: Comprehensive cleanup of ALL stale archives
    print("[Reset] Cleaning up remaining archives...")
    cleanup_count = 0
    
    # All files/dirs in archive that were NOT just restored
    # (Note: latest_db was copied, so it's still in archive. latest_grp was moved, so it's gone.)
    for item in ARCHIVE_DIR.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
            cleanup_count += 1
        except Exception as e:
            print(f"        Failed to delete {item.name}: {e}")

    if cleanup_count > 0:
        print(f"[Reset] Removed {cleanup_count} stale archive item(s).")
    
    # Try to remove ARCHIVE_DIR if empty
    try:
        if not any(ARCHIVE_DIR.iterdir()):
            ARCHIVE_DIR.rmdir()
            print("[Reset] Removed empty archive directory.")
    except Exception:
        pass

    print("[Reset] Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())