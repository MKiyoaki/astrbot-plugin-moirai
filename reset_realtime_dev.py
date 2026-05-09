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
        REALTIME_DB.unlink()
        print(f"[Reset] Deleted {REALTIME_DB.name}")
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
        shutil.copy2(str(latest_db), str(DATAFLOW_DB))
        print(f"[Reset] Restored {latest_db.name} → dataflow_test.db")
        if len(db_candidates) > 1:
            print(f"        ({len(db_candidates) - 1} older archive(s) retained)")

    # Step 3: Remove realtime-generated groups/ (summary files from this session)
    if GROUPS_DIR.exists():
        shutil.rmtree(str(GROUPS_DIR))
        print("[Reset] Removed realtime-generated .dev_data/groups/")

    # Step 4: Restore the original groups/ dir (moved by _archive_step at startup)
    grp_candidates = sorted(
        ARCHIVE_DIR.glob("groups_*"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not grp_candidates:
        print("[Reset] No archived groups_<ts>/ found — summary dir stays empty")
    else:
        latest_grp = grp_candidates[0]
        shutil.move(str(latest_grp), str(GROUPS_DIR))
        print(f"[Reset] Restored {latest_grp.name}/ → .dev_data/groups/")
        if len(grp_candidates) > 1:
            print(f"        ({len(grp_candidates) - 1} older archive(s) retained)")

    print("[Reset] Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
