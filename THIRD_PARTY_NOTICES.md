# Third-Party Notices

## Lucide (lucide.dev)

ISC License — Copyright (c) Lucide Contributors.

Added as a real npm dependency (`lucide-react`, published under the
project's standard dependency management — `web/package.json`, pinned
via `package-lock.json`), not vendored source. Chosen in T13.5c (Audit
Batch 1) as the single icon family for every icon in the app, replacing
the mix of hand-drawn inline SVGs and raw unicode glyphs (`✕`/`☰`/`✓`)
that existed before — `RiskBadge`, the Audience-tab icons, the mobile
nav toggle, the theme toggle, every expand/collapse chevron, the side
panel's close button, and the decorative arrows on in-page links. Icons
are imported as React components (tree-shaken, no runtime fetching);
`better-auth/better-icons`'s CLI (`npx better-icons search/get`) was
used only to find exact icon names during this task, not added as a
dependency or MCP config.

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

`progressive-blur.tsx` (`https://magicui.design/r/progressive-blur.json`) was vendored here in T13.5b and removed in T13.5c (Batch 0.9, 2026-10-10) when the developer's deployed-site review asked for the docked reasoning panel's top/bottom blur effect to come out entirely — no remaining call site, so the file was deleted rather than left unused.

Each depends only on this app's own `motion` dependency and a small local
`cn` helper (`web/lib/utils.ts`, clsx-based) added to satisfy their
`@/lib/utils` import — no other new dependency was introduced to use them.

## Kokonut UI (kokonutui.com) — checked, not vendored

The task's Kokonut addendum named three components (AI Loading, Mouse
Effect Card, Spotlight Cards) to add via the shadcn CLI if the repository
turned out to be MIT/Apache-2.0 licensed. Checked via `gh api
repos/kokonut-labs/kokonutui` (2026-10-09): GitHub reports
`"license":{"key":"mit","name":"MIT License",...}` — confirmed MIT. Each
component's actual registry JSON (`https://kokonutui.com/r/<name>.json`)
was then fetched and read in full before deciding whether to vendor it:

- `ai-loading.json` — license is fine, but its entire design is built
  around invented demo content (`TASK_SEQUENCES`: "Scanning web
  pages...", "Visiting 5 websites...", self-timed on a `setInterval`,
  unrelated to any real data) — exactly the "fake progress" the brief
  rules out for this exact feature, and not fixable by re-skinning it,
  since the fabrication is the component's entire design, not a surface
  detail. Not vendored. Built `web/components/ui/AILoadingSpinner.tsx`
  instead — a small decorative multi-ring spinner with no content of its
  own, paired with the real stage label (`lib/runStages.ts`'s
  `STAGE_LABEL`, the same names the API reports) via `ShimmerText`.
- `mouse-effect-card.json` — declares `registryDependencies: ["card",
  "button"]`, i.e. it expects shadcn/ui's own base primitives (and their
  own dependencies — class-variance-authority, @radix-ui/react-slot —
  not currently in this project), not just `motion`. Pulling those in
  would add packages beyond the task's explicit allow-list ("motion and
  next-themes"). Not vendored. Built `web/components/ui/MouseEffectCard.tsx`
  instead.
- `spotlight-cards.json` — declares a dependency on `lucide-react`, again
  beyond this addendum's own allow-list at the time. Not vendored. Built
  `web/components/ui/SpotlightCard.tsx` instead (two variants, per the
  brief). (`lucide-react` was later added as a real dependency in T13.5c,
  on a separate, explicit instruction naming it directly — see the
  Lucide section above; that doesn't retroactively change this
  decision, since `SpotlightCard.tsx` itself was deleted in that same
  T13.5c task, per the Update note below.)

No Kokonut source was copied into this repository — this section exists
to record that the license was checked and why each component was built
from scratch anyway, as the addendum's own fallback clause anticipates
("if the licence is missing or anything else, build our own equivalents
instead and say so" — generalized here to "or otherwise unusable without
exceeding the task's own dependency allow-list").

**Update, T13.5c (2026-10-10):** `GlowButton.tsx` and the two built-from-
scratch Kokonut equivalents named above — `MouseEffectCard.tsx` and
`SpotlightCard.tsx` (plus its `SpotlightGroup.tsx` coordination helper) —
were deleted in Batch 0.1/0.6, per the developer's deployed-site review
("remove the glow button everywhere"; "remove hover effects everywhere —
tilt, spotlight, glow, lift; plain cards"). No call site remained for any
of the four files, so they were removed rather than left unused; this
record stays as the history of why they existed in the first place.

## Hero image preparation — `web/scripts/prepare_hero.py` (dev-only, local)

T13.6's hero parallax layers (`web/public/hero/*.webp`) are processed from
a locally-generated source set (never committed raw) by a developer-run
script, never part of the deployed app. The task's brief named `rembg`
(MIT) as the preferred background-removal tool, with "a careful chroma-key
... if the licence is missing or anything else" as its own explicit
fallback.

**`rembg` was attempted first** (`uvx --from rembg rembg i <in> <out>`, no
project dependency added). It failed to install on this machine: one of
its transitive dependencies (`pymatting` → `numba` → `llvmlite`) has no
prebuilt wheel for this Python/platform combination and failed to build
from source (`llvmlite==0.50.0`'s own `build.py` exited non-zero via
`uv`'s isolated build environment). Not pursued further — the task's own
fallback clause covers exactly this case.

**Built instead:** a flood-fill chroma key, implemented directly in
`prepare_hero.py` using only `numpy` and `Pillow` (both already present in
this machine's Python 3.11 environment; neither is added to any
`package.json`/`pyproject.toml`, since this script runs outside both the
`web/` and `api/` dependency trees). The source fragments sit on a
near-uniform grey studio backdrop; a border-seeded flood fill in
color-distance space removes it, computed at a downscaled working
resolution and upsampled with bilinear interpolation for a naturally
anti-aliased edge. One real defect found and fixed during this process:
several renders have a soft off-axis light glow baked into the backdrop,
connected to the object by a faint color gradient — invisible to the eye
but bright enough to survive a tight threshold, and genuinely *connected*
to the object in color-space (not a separate blob — a true-separate-
component filter, tried first, was a no-op on it and actively broke the
scattered-pellet fragments, which legitimately have many disconnected
pieces). Fixed by widening the background-color threshold until the
glow's connecting gradient itself drops below it (swept 28→60 in steps of
6 on the worst-affected source image; 40 was the lowest clean value,
verified at full resolution across the whole set, not just that one
image) — see `prepare_hero.py`'s own `BG_THRESHOLD` comment for the full
account.

No third-party package is vendored or newly depended upon by this script.
