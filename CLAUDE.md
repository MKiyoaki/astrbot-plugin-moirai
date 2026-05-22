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

## Execution Rules

- You must first review the original test code and devise a plan, running tests while resolving the issue to ensure full functionality. Additionally, unless absolutely necessary, you are strictly prohibited from modifying any core framework code. In your plan, please break down the execution of this task into distinct phases and explain the rationale behind each action, including technical details. Once the plan is complete, please wait for my approval to proceed; you are not permitted to modify any code until the acceptance of plan.
- For testing frontend changes, use python run_webui_dev.py with cd "d:\Program Files\Git Lib\astrbot-plugin-enhanced-memory\web\frontend" npm run dev. After examined the functionality, push the frontend change to running environment.
- Lively write and renew the progress in TODO.md for clarifying the detail (following the grammar on top of TODO).
