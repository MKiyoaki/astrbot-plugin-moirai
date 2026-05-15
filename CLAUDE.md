# CLAUDE.md

## ABSOLUTE RULE — Working Directory

**All code changes must be made exclusively in this workspace:**

```
astrbot-plugin-enhanced-memory/
```

**Never modify any other directory**, including:
- Any other astrbot-related paths outside this workspace

## Build & Sync

- Frontend build: `conda activate plugin-dev`, then `npm run build` inside `web/frontend/`
- Sync static assets: `python tools/sync_frontend.py -f` from project root
