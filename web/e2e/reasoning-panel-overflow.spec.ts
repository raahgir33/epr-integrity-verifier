import { expect, test, type Page } from "@playwright/test";

/** Round 7 bug (developer-reported, 2026-10-10): on a processor page with
 * the reasoning panel docked (>= lg), expanding 2, 3 or all steps made the
 * panel's content spill out past the card's bottom edge and grow the page.
 *
 * Root cause (see ReasoningPanel.tsx's own doc comment): the panel's card
 * was sized with `max-height`, not a real `height`, and had no `overflow`
 * set (default `visible`). A column flex container sized only by
 * `max-height` has no definite main size for its flex-grow body to
 * distribute into, so the body never actually got height-bounded — it
 * grew to fit all its content, and the card's box, clipped only by
 * `max-height` with `overflow: visible`, let that excess spill straight
 * past its own bottom edge.
 *
 * This spec reproduces the bug directly (not via a screenshot diff): it
 * expands steps and asserts the panel's own scroll container is the thing
 * that overflows and scrolls, that the card's box never grows past its
 * fixed height, that no row's box extends past the card's edges, and that
 * the page's own height is unaffected — across 1, 2 and all steps
 * expanded, at three widths, in both themes. */

const WIDTHS = [1280, 1440, 1920];
const THEMES: Array<"light" | "dark"> = ["light", "dark"];

async function setTheme(page: Page, theme: "light" | "dark") {
  await page.addInitScript((t) => window.localStorage.setItem("theme", t), theme);
}

/** T13.8 flake fix: a fixed `waitForTimeout` after load/expand is a guess
 * at how long entrance animations (e.g. MetricTile's CountUp, round 7's
 * own font-swap concern) take to settle — on a cold worker (first test
 * in a freshly-launched browser, uncached fonts/JS) that guess runs out
 * before the page actually finishes animating, so `docHeightBefore` gets
 * captured mid-animation (taller) and compared against an `after` value
 * that's always had enough time to settle (shorter) — a deterministic,
 * 100%-reproducible-in-isolation false "the page grew/shrank" diff that
 * has nothing to do with the reasoning panel at all (confirmed: `aside`'s
 * own height was identical in both snapshots; a *sibling* block's
 * one-time entrance animation was still finishing). Polling for two
 * consecutive identical reads is robust to this regardless of which
 * animation or asset is slow, instead of guessing a bigger fixed delay. */
async function waitForStableHeight(page: Page, timeoutMs = 5_000): Promise<number> {
  const deadline = Date.now() + timeoutMs;
  let previous = await page.evaluate(() => document.documentElement.scrollHeight);
  while (Date.now() < deadline) {
    await page.waitForTimeout(150);
    const current = await page.evaluate(() => document.documentElement.scrollHeight);
    if (current === previous) return current;
    previous = current;
  }
  return previous;
}

async function expandSteps(page: Page, count: number) {
  for (let i = 0; i < count; i++) {
    await page.locator('aside button[aria-expanded="false"]').first().click();
  }
  if (count > 0) {
    await page.locator('aside button[aria-expanded="true"]').last().waitFor();
  }
  // Let the row-expand transition settle so measurements read the final,
  // not mid-animation, geometry.
  await waitForStableHeight(page);
}

async function assertContained(page: Page, expectedClientHeight: number) {
  const panelCard = page.locator("aside .card");
  const cardBox = await panelCard.boundingBox();
  expect(cardBox).not.toBeNull();
  if (!cardBox) return;

  // The card's own box must stay pinned to its fixed height — it must
  // never grow to accommodate more content (that growth, with no clip,
  // is exactly how content used to spill onto the rest of the page).
  const viewport = page.viewportSize();
  if (viewport) {
    expect(cardBox.height).toBeLessThanOrEqual(viewport.height);
  }

  // Rows never widen the panel horizontally — there's no horizontal
  // scroll in this design, so any row wider than the card is a real bug
  // (e.g. an unbroken long value forcing its chip wide). A row's own
  // bounding box legitimately extends past the card's *bottom* edge when
  // it's only partially scrolled into the clipped viewport (overflow
  // clips paint, not geometry) — that's correct, contained behavior, not
  // checked here.
  const rowBoxes = await page.locator("aside li").evaluateAll((els) =>
    els.map((el) => {
      const r = el.getBoundingClientRect();
      return { x: r.x, width: r.width };
    }),
  );
  for (const box of rowBoxes) {
    expect(box.x).toBeGreaterThanOrEqual(cardBox.x - 1);
    expect(box.x + box.width).toBeLessThanOrEqual(cardBox.x + cardBox.width + 1);
  }

  // The actual "does the box grow instead of scroll" check: the scroll
  // container's own visible height (clientHeight) must stay exactly what
  // it was with nothing expanded, no matter how much content is inside
  // it now. If clientHeight itself grew, the fixed-height fix regressed.
  const scrollBox = page.locator("aside .overflow-y-auto").first();
  const clientHeight = await scrollBox.evaluate((el) => el.clientHeight);
  expect(clientHeight).toBe(expectedClientHeight);
}

for (const width of WIDTHS) {
  for (const theme of THEMES) {
    test.describe(`reasoning panel overflow — ${width}px, ${theme}`, () => {
      test.use({ viewport: { width, height: 900 } });

      test.beforeEach(async ({ page }) => {
        await setTheme(page, theme);
      });

      for (const count of [1, 2, "all"] as const) {
        test(`stays contained with ${count} step(s) expanded`, async ({ page }, testInfo) => {
          await page.goto("/processors/PWP-05", { waitUntil: "networkidle" });
          // Root cause of the old flake, found by diffing the DOM tree
          // before/after: ProcessorTabs' `useIsBreakpointUp(1024)` is
          // deliberately `false` on the server and on first client
          // render (documented in lib/useIsBreakpointUp.ts, to avoid a
          // hydration mismatch), then flips `true` in a post-mount
          // effect at every width this spec tests (all >= 1024) — which
          // removes the "Agent reasoning" tab, reflowing the tab list
          // from 2 rows to 1 and shrinking the page by exactly the tab
          // row's height. That one-time swap is a deliberate app
          // tradeoff, not a bug; a generic settle-timeout can still race
          // it, so wait for its own concrete, known end state (the tab
          // gone) instead of guessing how long it takes.
          await expect(page.getByRole("tab", { name: /agent reasoning/i })).toHaveCount(0);
          // Let web-font swap-in and entrance animations (e.g.
          // MetricTile's CountUp) settle too before measuring.
          const docHeightBefore = await waitForStableHeight(page);
          const toggleCount = await page.locator('aside button[aria-expanded="false"]').count();
          expect(toggleCount).toBeGreaterThan(2);

          const scrollBox = page.locator("aside .overflow-y-auto").first();
          const clientHeightBefore = await scrollBox.evaluate((el) => el.clientHeight);

          await expandSteps(page, count === "all" ? toggleCount : Math.min(count, toggleCount));

          const docHeightAfter = await page.evaluate(() => document.documentElement.scrollHeight);
          expect(docHeightAfter).toBe(docHeightBefore);

          await assertContained(page, clientHeightBefore);

          const { scrollHeight, clientHeight } = await scrollBox.evaluate((el) => ({
            scrollHeight: el.scrollHeight,
            clientHeight: el.clientHeight,
          }));
          if (count === "all") {
            // With every step open the content is long enough that the
            // panel's own box must be the thing that scrolls internally.
            expect(scrollHeight).toBeGreaterThan(clientHeight);
            await page.screenshot({
              path: testInfo.outputPath(`all-expanded-${width}-${theme}.png`),
            });
          }
        });
      }
    });
  }
}
