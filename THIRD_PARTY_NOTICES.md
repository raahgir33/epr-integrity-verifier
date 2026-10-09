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
  beyond the allow-list. Not vendored. Built
  `web/components/ui/SpotlightCard.tsx` instead (two variants, per the
  brief).

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
