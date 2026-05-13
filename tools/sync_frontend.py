#!/usr/bin/env python3
"""Frontend Build & Sync Tool for Moirai.

This script builds the Next.js frontend and synchronizes the static output
to the AstrBot Plugin Pages directory (pages/moirai/).
"""

import sys
import logging
from pathlib import Path

# Add project root to sys.path so we can import core modules
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.utils.frontend_build import build_frontend, write_redirect_page

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger("sync-frontend")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Build and sync Moirai frontend")
    parser.add_argument("--force", "-f", action="store_true", help="Force rebuild even if output exists")
    parser.add_argument("--port", "-p", type=int, default=2655, help="WebUI port for the redirect page")
    args = parser.parse_args()

    logger.info("Starting frontend build and synchronization...")
    
    # 1. Build and Sync _app
    success = build_frontend(force=args.force)
    
    if not success:
        logger.error("Frontend build/sync failed. Check the logs above.")
        sys.exit(1)
        
    # 2. Update Redirect Page
    logger.info("Updating redirect page at pages/moirai/index.html (Port: %d)...", args.port)
    try:
        write_redirect_page(args.port)
        logger.info("Successfully updated redirect page.")
    except Exception as e:
        logger.error("Failed to write redirect page: %s", e)
        sys.exit(1)

    logger.info("All static assets are synchronized to pages/moirai/")

if __name__ == "__main__":
    main()
