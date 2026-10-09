# Third-Party Notices

Vendored component source, not published as a package dependency. Each file
listed here carries the same notice inline, at its top.

## Magic UI (magicui.design)

MIT License — Copyright (c) Magic UI.

Fetched from Magic UI's public component registry (`https://magicui.design/r/<name>.json`)
and placed unmodified (aside from the license header comment) under `web/components/magicui/`:

| File | Registry source |
|---|---|
| `web/components/magicui/animated-list.tsx` | `https://magicui.design/r/animated-list.json` |
| `web/components/magicui/typing-animation.tsx` | `https://magicui.design/r/typing-animation.json` |
| `web/components/magicui/progressive-blur.tsx` | `https://magicui.design/r/progressive-blur.json` |

Each depends only on this app's own `motion` dependency and a small local
`cn` helper (`web/lib/utils.ts`, clsx-based) added to satisfy their
`@/lib/utils` import — no other new dependency was introduced to use them.
