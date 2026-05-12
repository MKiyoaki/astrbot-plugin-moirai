# WebUI Module

Next.js 16 (App Router) + shadcn/ui frontend for the Enhanced Memory plugin.

## Structure

```
web/
├── frontend/          # Next.js source (edit here)
│   ├── app/           # App Router pages
│   ├── components/    # React components
│   │   ├── ui/        # shadcn/ui primitives
│   │   ├── layout/    # AppShell, AppSidebar, PageHeader
│   │   ├── events/    # EventTimeline, EventDialogs
│   │   ├── graph/     # CytoscapeGraph, PersonaDialogs
│   │   └── shared/    # LoginScreen, TagSelector, Toaster
│   ├── lib/           # api.ts, store.tsx, i18n.ts, utils.ts
│   └── (build artifacts go to pages/moirai/ at repo root)
├── server.py          # aiohttp backend — local debug only (webui_standalone_debug)
├── auth.py            # Auth helpers
└── registry.py        # Third-party panel registry
```

## Prerequisites — Development Environment

Node.js lives in the `node` conda environment:

```bash
export PATH="/Users/kiyoaki/miniconda3/envs/node/bin:$PATH"
```

Run this (or add to your shell profile) before any `npm` or `node` command.

## Development

```bash
export PATH="/Users/kiyoaki/miniconda3/envs/node/bin:$PATH"
cd web/frontend
npm install
npm run dev        # dev server with API proxy to backend on $BACKEND_PORT (default 2654)
```

## Build (required before deploying)

```bash
export PATH="/Users/kiyoaki/miniconda3/envs/node/bin:$PATH"
cd web/frontend
npm run build      # outputs to pages/moirai/ at repo root
```

The build output goes to `pages/moirai/` (AstrBot Plugin Pages standard). AstrBot serves these files and manages the HTTP port and auth. Always rebuild and commit the `pages/moirai/` directory after frontend changes.

## Key Conventions

- All UI strings in `lib/i18n.ts` — no hard-coded Chinese text in components.
- Persona confidence is **read-only** in the UI (ML-derived). Default for new personas is configurable in Settings (`em_default_persona_confidence`, default `0.5`).
- Searchable combobox pattern: Popover + Input + filtered list (see `TagSelector`, `EventInheritPicker`). No `Command` component.
- Event timeline uses shadcn `Card` grouped by thread — no SVG, no inline background colors.
- API calls go through `lib/api.ts`; all write operations require sudo mode.
