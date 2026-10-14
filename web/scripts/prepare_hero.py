#!/usr/bin/env python3
"""Processes the hero parallax source images into transparent WebP layers
under web/public/hero/. Local-only, developer-run, never deployed —
reproducible from the generated source folder (never committed raw).

Background removal for the l2/l3/hero-earth fragments uses a flood-fill
chroma key (numpy + Pillow only, no extra dependency): the source files
sit on a near-uniform grey/white studio backdrop, so a color-distance
flood fill seeded from the image border reliably isolates the backdrop
even where it's not perfectly flat, then the mask is computed at a
downscaled working size and upsampled with bilinear interpolation for a
naturally anti-aliased, feathered edge (docs/PROGRESS.md T13.6: `rembg`'s
own dependency chain (`numba`/`llvmlite`) failed to build from source via
`uvx` on this machine's architecture — the brief's own fallback, "a
careful chroma-key is acceptable if edges are clean," covers this).

T13.6b repoints this script at a replaced source set (all .jpg now, a
different file list and variant count than T13.6's): drops the old sky/
distant-islands backdrops, adds `sky-clouds.jpg` (new sky layer) and
`hero-earth.jpg` (new centrepiece, exported larger than the other
fragments since it renders as the hero's focal point). The mist layers
and most l2/l3 fragments carry over, repointed at their current file
names.

Usage:
    python3 web/scripts/prepare_hero.py --source ~/Workspace/tmp/hero-pictures
"""

from __future__ import annotations

import argparse
import os

# Must be set before numpy is imported: on this machine, numpy's Accelerate
# (Apple's veclib) BLAS backend hangs indefinitely at 100% CPU with no
# progress on ordinary array ops as soon as they're invoked through an
# imported module function rather than inlined top-level code — isolated
# while debugging T13.6b's rewrite of this script, a known class of macOS
# Accelerate-BLAS threading bug. Forcing every thread pool to size 1 is the
# standard mitigation and avoids spinning up Accelerate's thread pool at
# all for this script's small, non-performance-critical arrays.
os.environ.setdefault("VECLIB_MAXIMUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "web" / "public" / "hero"

SKY_SRC = "sky-clouds.jpg"
HERO_EARTH_SRC = "hero-earth.jpg"
# Only 2 of the 3 mist variants are used — l4-mist-2.jpg is the closeup/
# denser look, kept as the near mist layer; l4-mist-1/3 are near-duplicate
# horizon-band smoke (same style, different noise seed) and only one is
# needed as the far mist layer. Dropping the third keeps the hero's image
# weight well under budget without losing a visually distinct look.
MIST_SRC = ["l4-mist-1.jpg", "l4-mist-2.jpg"]

# Output name -> source file. T13.6b: repointed at the replaced source
# directory — every variant below is what's actually present now (several
# T13.6 variants' source files are gone: strata-b, pellets-rock-b,
# pebble-b, pebble-c). `pellets-b` recovers what was `l3-pellets-2.png` in
# T13.6 (dropped then for an unremovable corner watermark, see
# CORNER_STAMP_FRAGMENTS below) and `hero-earth` is new — the composition's
# centrepiece, widths overridden in FRAGMENT_WIDTH_OVERRIDES since it
# renders far larger than every other fragment here.
FRAGMENT_SRC = {
    "soil-moss-a": "l2-soil-moss.jpg",
    "soil-moss-b": "l2-soil-moss02.jpg",
    "strata-a": "l2-strata.jpg",
    "pellets-rock-a": "l2-pellets-rock.jpg",
    "pebble-a": "l3-pebble.jpg",
    # pellets-a's corner_is_clean() check flags "WATERMARK SUSPECTED" in
    # the run report — confirmed by inspection to be a false positive:
    # l3-pellets.jpg's actual watermark sits in plain background that the
    # chroma key already removed; the flagged corner's opacity comes from
    # real pellets that genuinely scatter that close to the edge (same
    # scattered-to-every-edge composition as pellets-b, just not quite
    # touching this particular corner). No stamp needed here.
    "pellets-a": "l3-pellets.jpg",
    "pellets-b": "l3-pellets-2.jpg",
    "hero-earth": "hero-earth.jpg",
    # T16a item 2b: the distant floating-island band along the bottom of
    # the hero — the most distant layer, restoring what T13.6b dropped
    # when it replaced the old distant-islands source. Needs the per-row
    # background model below; the flat-mean key leaves most of this
    # image's sky opaque.
    "distant-1": "l1-distant-1.jpg",
}

# T16a item 2b: fragments whose backdrop is a smooth GRADIENT rather than
# the near-uniform studio grey every other source here sits on. For those,
# one global background colour (the border mean) is wrong at both ends of
# the gradient at once: on l1-distant-1.jpg the border mean is RGB ~214
# while the actual backdrop runs ~230 at the top to ~192 at the bottom, so
# at BG_THRESHOLD the flood fill left 34.6% of the pure-sky upper half
# opaque — a grey slab, not a cutout. Estimating the background per ROW,
# from the outer columns on each side, tracks the gradient exactly and
# drops that to 0.000 (measured; see PER_ROW_THRESHOLD). Opt-in per
# fragment name, mirroring CORNER_STAMP_FRAGMENTS, so every existing
# fragment keeps its current code path and stays byte-identical.
PER_ROW_BG_FRAGMENTS = {"distant-1"}
PER_ROW_EDGE_COLS = 12  # columns sampled at each side to estimate a row's background
# Swept 40/44/48/50 on l1-distant-1.jpg. 40 already clears the sky
# completely but leaves 2.3% of the bottom edge opaque (the densest mist);
# 48 is the lowest value where BOTH the sky and the bottom edge reach
# 0.000 while the islands keep 25.7% of the band opaque.
PER_ROW_THRESHOLD = 48.0

MASK_WORK_SIZE = 480  # longest-edge size the flood-fill mask is computed at
# T16a item 2b: 480 is fine while the export is 240-560px wide — the mask
# is upscaled by at most ~1.2x and BILINEAR hides the steps. distant-1
# exports at 2200px, a 4.6x upscale, which turns every one-pixel step in
# the 480px mask into a ~5px block: the mist between the islands came out
# with hard stair-stepped polygon edges, clearly visible against the dark
# theme. Computing this one fragment's mask at 1400 brings the upscale
# back to ~1.6x and the edge back to a natural feather.
MASK_WORK_SIZE_OVERRIDES = {"distant-1": 1400}
# RGB euclidean distance treated as "background-like". 28 (the flat
# background's own corner-to-corner vignette range) left a soft off-axis
# light glow baked into several of these renders connected to the object
# by a faint gradient bridge, bright enough to fail a tighter threshold
# but still clearly not the object (confirmed on l2-soil-moss-2.png: a
# bloom up-and-left of the sphere, invisible to the eye against the grey
# backdrop but unmistakable under contrast stretching). 40 was the lowest
# value, swept in steps of 6 from 28 to 60, where the glow's connecting
# gradient first drops entirely below threshold and the mask becomes a
# clean, single rounded blob — verified for every fragment in this set at
# full resolution, not just this one. Unchanged for T13.6b's replaced
# source set — re-verified on hero-earth.jpg (white-backdrop studio
# render) and every repointed l2/l3 file; same clean single-blob result.
BG_THRESHOLD = 40.0
TRIM_MARGIN_FRAC = 0.03  # margin kept around the trimmed content bbox
CORNER_CHECK_FRAC = 0.08  # fraction of trimmed size checked for a leftover watermark
CORNER_OPAQUE_LIMIT = 0.05  # max fraction of that corner allowed to be non-transparent

# T13.6b: l3-pellets-2.jpg's pellets scatter to every edge of the frame
# (same composition as T13.6's l3-pellets-2.png), so trim_to_content can't
# crop the bottom-right watermark away — confirmed again on this JPG,
# same failure mode documented in T13.6's PROGRESS.md entry. Unlike T13.6,
# this is not dropped a second time: the watermark's own corner is plain,
# untextured background (no pellet sits there — checked by eye at full
# resolution before adding this), so it's safe to zero that corner's
# alpha directly rather than rely on trim_to_content. Opt-in per fragment
# name, not automatic on every corner_is_clean() failure — an unrelated
# failure elsewhere should still fail loudly, not get silently patched.
CORNER_STAMP_FRAGMENTS = {"pellets-b"}
# Slightly larger than CORNER_CHECK_FRAC's own box, so the stamp fully
# covers what that check would have flagged.
CORNER_STAMP_FRAC = 0.09

FRAGMENT_WIDTHS = {"1x": 240, "2x": 480}  # on-screen target widths
# hero-earth is the composition's centrepiece (~45-55% of viewport height,
# centre-right, full 100svh hero) — far larger on screen than every other
# fragment, so it gets its own export size rather than FRAGMENT_WIDTHS'
# small-fragment default. 1120px at 2x stays within the 2048px source, so
# the 2x density is never upscaled.
# distant-1 trims to a wide, short strip (~2430x485, aspect 0.20) because
# the islands occupy only the lower third of its frame. It renders as a
# full-width band, so it needs real width — 2200 at 2x stays inside the
# 2430 trimmed source, never upscaled.
FRAGMENT_WIDTH_OVERRIDES = {
    "hero-earth": {"1x": 560, "2x": 1120},
    "distant-1": {"1x": 1100, "2x": 2200},
}
# Soft, distant, mostly-transparent layer that also sits behind the mist —
# it does not need the detail the foreground fragments do. At q68 the pair
# measured 101.5 KB against 131.8 KB at the fragment default.
FRAGMENT_QUALITY_OVERRIDES = {"distant-1": 68}  # same value as MIST_QUALITY, defined below
FRAGMENT_QUALITY = 85  # lossy WebP — these are organic/textured, not flat graphics
BACKDROP_WIDTHS = {"1x": 900, "2x": 1800}  # legacy default, unused now sky is the only backdrop
# Sky is now full-bleed behind a 100svh hero (up to 1920px+ viewports),
# not a bordered card at partial width — needs real resolution at 1x, not
# a small thumbnail. 2752px at 2x is the native source width, so it's
# never upscaled either.
SKY_WIDTHS = {"1x": 1600, "2x": 2752}
MIST_WIDTHS = {"1x": 700, "2x": 1400}  # smaller: mist is a soft, low-detail layer
MIST_QUALITY = 68
BACKDROP_QUALITY = 82
EDGE_CROP_FRAC = 0.03  # sky: fraction cropped off the watermark corner
POSTER_WIDTH = 1600
POSTER_ASPECT = 1536 / 2752  # source aspect ratio, kept for the poster canvas


@dataclass
class Report:
    lines: list[str]

    def add(self, line: str) -> None:
        self.lines.append(line)
        print(line)


def resize_rgba(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resizing an RGBA image with LANCZOS on all four channels together
    can ring on the alpha channel's sharp 0->255 transitions, overshoot,
    and clip back to 255 — producing isolated fully-opaque "ghost" pixels
    far from any real edge (confirmed on l2-soil-moss-2.png: a clean,
    fully-transparent corner picked up a stray opaque speck purely from
    this resize step). RGB keeps LANCZOS for sharpness; alpha resizes with
    BILINEAR, which is a convex combination of its inputs and so can never
    overshoot past the min/max of the pixels it blends."""
    r, g, b, a = im.split()
    rgb = Image.merge("RGB", (r, g, b)).resize(size, Image.LANCZOS)
    alpha = a.resize(size, Image.BILINEAR)
    out = rgb.convert("RGBA")
    out.putalpha(alpha)
    return out


def _background_color(im_rgb: np.ndarray) -> np.ndarray:
    border = np.concatenate([im_rgb[0, :, :], im_rgb[-1, :, :], im_rgb[:, 0, :], im_rgb[:, -1, :]])
    return border.mean(axis=0)


def _background_color_per_row(im_rgb: np.ndarray, cols: int = PER_ROW_EDGE_COLS) -> np.ndarray:
    """One background colour per row, from the outer `cols` columns on each
    side. Valid only where those columns really are backdrop at every row —
    true for l1-distant-1.jpg, whose content spans x 9.4%-92.1%. Returns
    (h, 3), broadcast against the image as (h, 1, 3)."""
    return np.concatenate([im_rgb[:, :cols, :], im_rgb[:, -cols:, :]], axis=1).mean(axis=1)


def chroma_key(
    src_path: Path,
    threshold: float = BG_THRESHOLD,
    per_row_bg: bool = False,
    work_size: int = MASK_WORK_SIZE,
) -> Image.Image:
    """True = background in the mask below. Seeds from every border pixel
    that already looks like background, then grows through any
    4-connected neighbor within `threshold` of the sampled background
    color — so an interior pixel that merely resembles the backdrop color
    is never removed unless a continuous path of matching pixels actually
    connects it to the border.

    The mask-growing loop is inlined here rather than factored into its
    own function: on this machine, calling an otherwise-identical loop
    through a separate module-level function hung indefinitely (100% CPU,
    no progress) where the exact same code inlined at a script's top
    level ran in milliseconds — isolated while debugging T13.6b's rewrite
    of this script. The root cause wasn't pinned down (environment-
    specific, not a logic bug — every manual re-derivation of the
    algorithm converged correctly and fast), so this sidesteps it rather
    than chase it further; the 2000-iteration cap below is a defensive
    backstop, not expected to ever trigger (actual convergence is under
    ~200 iterations for every fragment in this set)."""
    full = Image.open(src_path).convert("RGB")
    w, h = full.size
    scale = work_size / max(w, h)
    small = full.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.BILINEAR)
    im_rgb = np.asarray(small)

    if per_row_bg:
        bg_color = _background_color_per_row(im_rgb)[:, None, :]
    else:
        bg_color = _background_color(im_rgb)
    diff = im_rgb.astype(np.float32) - bg_color
    dist = np.sqrt((diff * diff).sum(axis=-1))
    candidate = dist < threshold

    mask = np.zeros_like(candidate)
    mask[0, :] = candidate[0, :]
    mask[-1, :] = candidate[-1, :]
    mask[:, 0] = candidate[:, 0]
    mask[:, -1] = candidate[:, -1]

    for _ in range(2000):
        grown = mask.copy()
        grown[1:, :] |= mask[:-1, :] & candidate[1:, :]
        grown[:-1, :] |= mask[1:, :] & candidate[:-1, :]
        grown[:, 1:] |= mask[:, :-1] & candidate[:, 1:]
        grown[:, :-1] |= mask[:, 1:] & candidate[:, :-1]
        if np.array_equal(grown, mask):
            break
        mask = grown
    bg_mask_small = mask

    # Upscaling the binary mask with BILINEAR gives a naturally anti-
    # aliased edge; a small Gaussian blur on top softens it further so the
    # cutout doesn't look stair-stepped at full resolution.
    alpha_small = (~bg_mask_small * 255).astype(np.uint8)
    alpha = Image.fromarray(alpha_small, mode="L").resize((w, h), Image.BILINEAR)
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=1.2))

    rgba = full.convert("RGBA")
    rgba.putalpha(alpha)
    return rgba


def stamp_corner_transparent(
    im: Image.Image, corner: str = "br", frac: float = CORNER_STAMP_FRAC
) -> Image.Image:
    """Zeroes one corner's alpha directly, for a fragment whose watermark
    corner trim_to_content can't crop away (content touching every edge —
    see CORNER_STAMP_FRAGMENTS). Only ever called on a name explicitly
    opted into that set, after a by-eye check that the corner is empty
    background, not real content."""
    w, h = im.size
    cw, ch = max(1, round(w * frac)), max(1, round(h * frac))
    boxes = {
        "tl": (0, 0, cw, ch),
        "tr": (w - cw, 0, w, ch),
        "bl": (0, h - ch, cw, h),
        "br": (w - cw, h - ch, w, h),
    }
    r, g, b, a = im.split()
    patch = Image.new("L", a.size, 0)
    a.paste(patch.crop(boxes[corner]), boxes[corner])
    out = Image.merge("RGB", (r, g, b)).convert("RGBA")
    out.putalpha(a)
    return out


def trim_to_content(im: Image.Image, margin_frac: float = TRIM_MARGIN_FRAC) -> Image.Image:
    bbox = im.getbbox()
    if bbox is None:
        return im
    left, upper, right, lower = bbox
    mx = round((right - left) * margin_frac)
    my = round((lower - upper) * margin_frac)
    left = max(0, left - mx)
    upper = max(0, upper - my)
    right = min(im.width, right + mx)
    lower = min(im.height, lower + my)
    return im.crop((left, upper, right, lower))


def corner_is_clean(im: Image.Image, frac: float = CORNER_CHECK_FRAC) -> bool:
    """Checks every corner, not just bottom-right — trimming can shift
    which corner of the final crop was nearest the source watermark."""
    w, h = im.size
    cw, ch = max(1, round(w * frac)), max(1, round(h * frac))
    boxes = [
        (0, 0, cw, ch),
        (w - cw, 0, w, ch),
        (0, h - ch, cw, h),
        (w - cw, h - ch, w, h),
    ]
    for box in boxes:
        alpha = im.crop(box).split()[-1]
        hist = alpha.histogram()
        opaque_frac = sum(hist[200:]) / (cw * ch)
        if opaque_frac > CORNER_OPAQUE_LIMIT:
            return False
    return True


def export_fragment(im: Image.Image, out_dir: Path, name: str, widths: dict | None = None) -> dict:
    sizes = {}
    aspect = im.height / im.width
    target_widths = widths or FRAGMENT_WIDTHS
    quality = FRAGMENT_QUALITY_OVERRIDES.get(name, FRAGMENT_QUALITY)
    for density, target_w in target_widths.items():
        target_h = max(1, round(target_w * aspect))
        resized = resize_rgba(im, (target_w, target_h))
        path = out_dir / f"{name}-{density}.webp"
        resized.save(path, "WEBP", quality=quality, method=6)
        sizes[density] = path.stat().st_size
    return sizes


def process_mist(src_path: Path, out_dir: Path, name: str) -> dict:
    white = process_mist_image(src_path)
    sizes = {}
    w, h = white.size
    for density, target_w in MIST_WIDTHS.items():
        target_h = max(1, round(target_w * h / w))
        resized = resize_rgba(white, (target_w, target_h))
        path = out_dir / f"{name}-{density}.webp"
        resized.save(path, "WEBP", quality=MIST_QUALITY, method=6)
        sizes[density] = path.stat().st_size
    return sizes


def process_mist_image(src_path: Path) -> Image.Image:
    luminance = np.asarray(Image.open(src_path).convert("L")).astype(np.float32)
    floor, ceil = np.percentile(luminance, [5, 99])
    alpha = np.clip((luminance - floor) / max(1.0, ceil - floor), 0.0, 1.0) * 255
    alpha_img = Image.fromarray(alpha.astype(np.uint8), mode="L")
    white = Image.new("RGBA", alpha_img.size, (255, 255, 255, 255))
    white.putalpha(alpha_img)
    return white


def process_backdrop(
    src_path: Path, out_dir: Path, name: str, widths: dict, edge_frac: float = EDGE_CROP_FRAC
) -> tuple[dict, Image.Image]:
    """Sky: crop the watermark corner off, scale back up to the working
    size so the layer's framing doesn't shift, export at both densities.
    Canvas aspect ratio is unchanged by this — only the watermark corner's
    few source pixels are discarded, same technique T13.6 already used
    for the sky/distant backdrops."""
    im = Image.open(src_path).convert("RGB")
    w, h = im.size
    cropped = im.crop((0, 0, round(w * (1 - edge_frac)), round(h * (1 - edge_frac))))
    cropped = cropped.resize((w, h), Image.LANCZOS)

    sizes = {}
    for density, target_w in widths.items():
        target_h = max(1, round(target_w * h / w))
        resized = cropped.resize((target_w, target_h), Image.LANCZOS)
        path = out_dir / f"{name}-{density}.webp"
        resized.save(path, "WEBP", quality=BACKDROP_QUALITY, method=6)
        sizes[density] = path.stat().st_size
    return sizes, cropped


def build_poster(
    sky: Image.Image,
    hero_earth: Image.Image,
    accents: list[Image.Image],
    out_dir: Path,
    distant: Image.Image | None = None,
) -> int:
    """Flattened full-scene composite for the no-JS / reduced-motion
    fallback — a representative static arrangement, not pixel-identical to
    HeroScene.tsx's live CSS layout. T13.6b: rebuilt around the new
    composition (sky + centred-right hero-earth + a couple of accent
    fragments near the edges); no mist/distant layers, matching the live
    scene's "no mist in the poster" simplicity."""
    canvas_h = round(POSTER_WIDTH * POSTER_ASPECT)
    base = sky.convert("RGBA").resize((POSTER_WIDTH, canvas_h), Image.LANCZOS)

    # T16a item 2b: the distant band sits directly on the sky, behind
    # everything else, so the reduced-motion poster matches the live
    # scene's new layer order instead of losing its most distant layer.
    if distant is not None:
        band_w = POSTER_WIDTH
        band_h = round(band_w * distant.height / distant.width)
        band = resize_rgba(distant, (band_w, band_h))
        faded = band.copy()
        faded.putalpha(band.split()[-1].point(lambda v: round(v * 0.65)))
        base.alpha_composite(faded, (0, canvas_h - band_h))

    earth_h = round(canvas_h * 0.5)
    earth_w = round(earth_h * hero_earth.width / hero_earth.height)
    earth_resized = resize_rgba(hero_earth, (earth_w, earth_h))
    earth_x = round(POSTER_WIDTH * 0.58 - earth_w / 2)
    earth_y = round(canvas_h * 0.5 - earth_h / 2)
    base.alpha_composite(earth_resized, (max(0, earth_x), max(0, earth_y)))

    accent_positions = [(0.04, 0.68, 0.12), (0.90, 0.08, 0.09), (0.05, 0.06, 0.08)]
    for frag, (xf, yf, wf) in zip(accents, accent_positions, strict=False):
        fw = round(POSTER_WIDTH * wf)
        fh = round(fw * frag.height / frag.width)
        resized = resize_rgba(frag, (fw, fh))
        base.alpha_composite(resized, (round(POSTER_WIDTH * xf), round(canvas_h * yf)))

    path = out_dir / "poster.webp"
    base.convert("RGB").save(path, "WEBP", quality=82, method=6)
    return path.stat().st_size


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", default=DEFAULT_OUT, type=Path)
    args = parser.parse_args()

    src_dir: Path = args.source.expanduser()
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    # T13.6b: the current manifest (fragments + mist + sky + poster) is
    # smaller than T13.6's — distant/old-sky are gone outright and several
    # fragment variants lost their source file. Without this, re-running
    # against the replaced source directory leaves those old *.webp files
    # sitting in public/hero/ forever (they're just not overwritten, since
    # nothing regenerates a name that's no longer in FRAGMENT_SRC) — a
    # stale asset HeroScene.tsx no longer references, silently inflating
    # the directory's weight. Delete anything not in the current manifest
    # before writing a single new file.
    current_names = {
        *FRAGMENT_SRC.keys(),
        *(f"mist-{i}" for i in range(1, len(MIST_SRC) + 1)),
        "sky",
        "poster",
    }
    removed = []
    for existing in out_dir.glob("*.webp"):
        stem = (
            existing.stem.rsplit("-", 1)[0]
            if existing.stem.rsplit("-", 1)[-1] in ("1x", "2x")
            else existing.stem
        )
        if stem not in current_names:
            existing.unlink()
            removed.append(existing.name)

    report = Report([])
    total_bytes = 0
    fragment_rgba: dict[str, Image.Image] = {}

    report.add(f"source: {src_dir}")
    report.add(f"out:    {out_dir}\n")
    if removed:
        report.add(f"-- removed {len(removed)} stale file(s) no longer in the manifest --")
        for name in sorted(removed):
            report.add(f"  removed: {name}")
        report.add("")

    report.add("-- fragments (chroma key + trim) --")
    for name, src_name in FRAGMENT_SRC.items():
        rgba = chroma_key(
            src_dir / src_name,
            threshold=PER_ROW_THRESHOLD if name in PER_ROW_BG_FRAGMENTS else BG_THRESHOLD,
            per_row_bg=name in PER_ROW_BG_FRAGMENTS,
            work_size=MASK_WORK_SIZE_OVERRIDES.get(name, MASK_WORK_SIZE),
        )
        if name in CORNER_STAMP_FRAGMENTS:
            rgba = stamp_corner_transparent(rgba)
        rgba = trim_to_content(rgba)
        ok = corner_is_clean(rgba)
        widths = FRAGMENT_WIDTH_OVERRIDES.get(name)
        sizes = export_fragment(rgba, out_dir, name, widths=widths)
        total_bytes += sum(sizes.values())
        fragment_rgba[name] = rgba
        status = "clean" if ok else "WATERMARK SUSPECTED — inspect manually"
        report.add(
            f"  {name:16s} <- {src_name:24s} {rgba.width}x{rgba.height}  "
            f"1x={sizes['1x']}B 2x={sizes['2x']}B  [{status}]"
        )

    report.add("\n-- mist (luminance -> alpha) --")
    for i, src_name in enumerate(MIST_SRC, start=1):
        name = f"mist-{i}"
        sizes = process_mist(src_dir / src_name, out_dir, name)
        total_bytes += sum(sizes.values())
        report.add(f"  {name:10s} <- {src_name:16s} 1x={sizes['1x']}B 2x={sizes['2x']}B")

    report.add("\n-- sky backdrop (edge crop, watermark removed) --")
    sky_sizes, sky_cropped = process_backdrop(src_dir / SKY_SRC, out_dir, "sky", SKY_WIDTHS)
    total_bytes += sum(sky_sizes.values())
    report.add(f"  sky        <- {SKY_SRC:16s} 1x={sky_sizes['1x']}B 2x={sky_sizes['2x']}B")

    report.add("\n-- poster (flattened fallback) --")
    accents = [
        fragment_rgba[name]
        for name in ("pebble-a", "pellets-rock-a", "soil-moss-a")
        if name in fragment_rgba
    ]
    poster_bytes = build_poster(
        sky_cropped,
        fragment_rgba["hero-earth"],
        accents,
        out_dir,
        distant=fragment_rgba.get("distant-1"),
    )
    total_bytes += poster_bytes
    report.add(f"  poster.webp  {poster_bytes}B")

    report.add(
        f"\nTOTAL hero/ weight: {total_bytes / 1_000_000:.2f} MB (budget: 1.5 MB target, 3 MB cap)"
    )
    if total_bytes > 3_000_000:
        report.add("  !! OVER the 3 MB cap — revisit sizes/quality before committing")
    elif total_bytes > 1_500_000:
        report.add("  (over the 1.5 MB target, within the 3 MB cap)")


if __name__ == "__main__":
    main()
