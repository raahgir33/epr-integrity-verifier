# Third-Party Notices

## Fonts

### Noto Sans Devanagari

SIL Open Font License 1.1 — Copyright 2022 The Noto Project Authors.

Used to render Hindi text correctly in generated synthetic documents
(`assets/fonts/NotoSansDevanagari-Regular.ttf`, headless-Chromium
rendering) and in the web app (`web/public/fonts/NotoSansDevanagari-Regular.ttf`,
for Hindi strings shown in the UI, e.g. clarification memos). License
text ships alongside the font (`*-OFL.txt`).

### Kalam

SIL Open Font License 1.1 — Copyright 2011-2013 Rajesh Jinaga Ramamurthy
and the Kalam Project Authors.

Used for the handwriting-style annotations in generated synthetic
documents (`assets/fonts/Kalam-Regular.ttf`). License text ships
alongside the font (`assets/fonts/Kalam-OFL.txt`).

Typefaces loaded at runtime through `next/font/google` (Google Sans,
Google Sans Code, Inter) are served by Google Fonts and not vendored
here, so they carry no file in this repository to attribute.

## Data and imagery

### Sentinel-2 imagery and Open Buildings

"Contains modified Copernicus Sentinel data" and Open Buildings v3
(Google Research, CC BY 4.0) — both used by `geo/site.py` (C8 site
plausibility) and attributed in the app itself, on `/method`.

### Hero imagery

The hero's parallax layers (`web/public/hero/*.webp`) are processed from
a locally-generated source set by `web/scripts/prepare_hero.py`, a
dev-only script that is never part of the deployed app. Credited in the
app on `/method` and in the site footer.

## Lucide (lucide.dev)

ISC License — Copyright (c) Lucide Contributors.

Added as a real npm dependency (`lucide-react` in `web/package.json`,
pinned via `package-lock.json`), not vendored source. Icons are imported
as React components, tree-shaken, with no runtime fetching.

`better-auth/better-icons`'s CLI (`npx better-icons search/get`) was used
only to look up exact icon names during development; it is not a
dependency of this project and no MCP config was added for it.

Vendored component source (not published as a package dependency) is
listed below. Each such file carries the same notice inline, at its top.

## Magic UI (magicui.design)

MIT License — Copyright (c) Magic UI.

Fetched from Magic UI's public component registry (`https://magicui.design/r/<name>.json`)
and placed unmodified (aside from the license header comment) under `web/components/magicui/`:

| File | Registry source |
|---|---|
| `web/components/magicui/animated-list.tsx` | `https://magicui.design/r/animated-list.json` |
| `web/components/magicui/typing-animation.tsx` | `https://magicui.design/r/typing-animation.json` |

Each depends only on this app's own `motion` dependency and a small local
`cn` helper (`web/lib/utils.ts`, clsx-based) added to satisfy their
`@/lib/utils` import — no other new dependency was introduced to use them.

## Kokonut UI (kokonutui.com) — checked, not vendored

License confirmed MIT via `gh api repos/kokonut-labs/kokonutui`
(2026-10-09). Three components (AI Loading, Mouse Effect Card, Spotlight
Cards) were evaluated from their registry JSON and none was vendored —
equivalents were built in this repository instead. **No Kokonut source
was copied into this repository.** This section exists only to record
that the license was checked, as the originating task's brief asked.

## rembg — considered, not used

`rembg` (MIT) was the background-removal tool named by the hero-imagery
task's brief. It could not be installed on this machine (a transitive
dependency failed to build from source), so it was never added as a
dependency and none of its code is present here. The brief's own
fallback was used instead: a chroma key implemented directly in
`web/scripts/prepare_hero.py` using `numpy` and `Pillow`, both already
present in the local Python environment and neither added to any
`package.json`/`pyproject.toml` — that script runs outside both the
`web/` and `api/` dependency trees.

No third-party package is vendored or newly depended upon by this script.
