# Next.js template

This is a Next.js template with shadcn/ui.

## Adding components

To add components to your app, run the following command:

```bash
npx shadcn@latest add button
```

This will place the ui components in the `components` directory.

## Using components

To use the components in your app, import them as follows:

```tsx
import { Button } from "@/components/ui/button";
```

## Event summary views

`lib/utils.ts` parses topic-local summary fields for the event stream and database details. Missing fields are hidden; legacy Markdown escaping is cleaned without rendering HTML. Run `node tests/event-summary-ui.cjs` from the Moirai root for parser and component-rendering regressions, then `npm run typecheck` here. See [the event summary contract](../../docs/event-summary.md) for the extraction rules and realtime preview workflow.

## Event thread paging

An unspooled spindle draws its filtered events into one SVG thread. Above 200 events (`THREAD_PAGE_SIZE` in `app/events/page.tsx`) the thread shows one page of 200 at a time, and `components/events/thread-pager.tsx` appears to the right of the time-gap button. Changing the spindle, search, date range, or tags returns to page 1. A focus or highlight restored from another page, and an event picked in the detail panel, move to the page that holds it. After changing this view, run `npm run typecheck`, `npm run build`, and sync `out/` to `pages/moirai/_app/`.

## Interaction tag tree

The shared Events/Library filter bar opens a read-only interaction Tag Tree from its coloured tag button. It loads `/api/tags/tree` when opened, passing the active Bot-persona scope, and renders the nine static groups plus approved custom leaves. Keep taxonomy data on the backend rather than duplicating it in frontend source. After changing this view, run `npm run typecheck`, `npm run build`, and sync `out/` to `pages/moirai/_app/` so `run_realtime_dev.py` serves the updated production assets.

## Relationship graph communities

The Graph page uses weighted Leiden clustering when the Leiden control is enabled. The resolution slider changes the granularity: larger values generally produce more, smaller communities. Clustering uses the selected edge weight source (affinity, message count, or equal), so changing that source can change both layout and community membership. The graph canvas and GEXF/CSV exports use the same community IDs. Identical inputs produce identical IDs. Community colors come from `getClusterColor()` in `lib/colors.ts`: the theme's `--color-palette-1` is rotated around the OKLCH hue wheel, split evenly by the community count, so colors never repeat and more communities means a smaller hue step. The largest community keeps the theme color, a coprime stride keeps size-ranked neighbours far apart on the wheel, and chroma has a 0.08 floor so the grayscale Nox theme still separates communities. Because the wheel is re-divided whenever the community count changes, other colors shift when the resolution changes the count. Resolution 1.0 is the current default; a local 75-node, 598-pair graph produced four affinity-weighted communities at that setting and nine at 1.5.

Sentiment edge coloring (`lib/sentiment-color.ts`) is relative to the pairs on screen. The pair value (the B or P axis, averaged over both directions) is divided by the 95th percentile of |value| across the visible pairs, with a 0.02 floor, and quantised into four levels on each side of neutral. The canvas, arrow markers, node detail values, and GEXF/CSV/image exports share that scale and its concrete hex colors. A color therefore means "strong relative to this view", not a fixed B/P threshold, and the mapping stays valid if the backend changes the value range.

Run `node --test tests/leiden-graph.cjs` from the Moirai root to check connectivity, deterministic output, resolution, weight sources, local node optimality, export fields, and performance. From `web/frontend/`, run `npm run typecheck`, `npm run lint -- lib/leiden.ts lib/graph-utils.ts app/graph/page.tsx components/graph/network-graph.tsx`, and `npm run build`. Copy the generated `out/` tree into `pages/moirai/_app/` after a successful build.
