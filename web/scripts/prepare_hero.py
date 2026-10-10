#!/usr/bin/env python3
"""Processes the hero parallax source images into transparent WebP layers
under web/public/hero/. Local-only, developer-run, never deployed —
reproducible from the generated source folder (never committed raw).

Background removal for the l2/l3 fragments uses a flood-fill chroma key
(numpy + Pillow only, no extra dependency): the source files sit on a
near-uniform grey studio backdrop, so a color-distance flood fill seeded
from the image border reliably isolates the backdrop even where it's not
perfectly flat, then the mask is computed at a downscaled working size and
upsampled with bilinear interpolation for a naturally anti-aliased,
feathered edge (docs/PROGRESS.md T13.6: `rembg`'s own dependency chain
(`numba`/`llvmlite`) failed to build from source via `uvx` on this
machine's architecture — the brief's own fallback, "a careful chroma-key
is acceptable if edges are clean," covers this).

Usage:
    python3 web/scripts/prepare_hero.py --source ~/Workspace/tmp/hero-pictures
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO_ROOT / "web" / "public" / "hero"

SKY_SRC = "l0-sky.png"
DISTANT_SRC = "l1-distant.png"
# Only 2 of the 3 mist variants are used — l4-mist-2.png is the closeup/
# denser look, kept as the near mist layer; l4-mist-1/3 are near-duplicate
# horizon-band smoke (same style, different noise seed) and only one is
# needed as the far mist layer. Dropping the third keeps the hero's image
# weight well under budget without losing a visually distinct look.
MIST_SRC = ["l4-mist-1.png", "l4-mist-2.png"]

# Output name -> source file. Every l2/l3 variant is kept EXCEPT
# l3-pellets-2.png: unlike every other fragment (one centered object, clear
# margin), its pellets scatter to every edge of the frame, so "trim to
# content" can't crop it at all, and its corner watermark sits in isolated
# transparent background (not connected to the flood-filled region) where
# it can't be safely removed without risking real pellets — confirmed by
# inspection (docs/PROGRESS.md T13.6). The other two pellets variants don't
# have this problem, so the pellets slot still gets 2 variants.
FRAGMENT_SRC = {
    "soil-moss-a": "l2-soil-moss-2.png",
    "soil-moss-b": "l2-soil-moss-3.png",
    "strata-a": "l2-strata.png",
    "strata-b": "l2-strata-2.png",
    "pellets-rock-a": "l2-pellets-rock.png",
    "pellets-rock-b": "l2-pellets-rock-2.png",
    "pebble-a": "l3-pebble.png",
    "pebble-b": "l3-pebble-2.png",
    "pebble-c": "l3-pebble-3.png",
    "pellets-a": "l3-pellets.png",
    "pellets-c": "l3-pellets-3.png",
}

MASK_WORK_SIZE = 480  # longest-edge size the flood-fill mask is computed at
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
# full resolution, not just this one.
BG_THRESHOLD = 40.0
TRIM_MARGIN_FRAC = 0.03  # margin kept around the trimmed content bbox
CORNER_CHECK_FRAC = 0.08  # fraction of trimmed size checked for a leftover watermark
CORNER_OPAQUE_LIMIT = 0.05  # max fraction of that corner allowed to be non-transparent

FRAGMENT_WIDTHS = {"1x": 240, "2x": 480}  # on-screen target widths
FRAGMENT_QUALITY = 85  # lossy WebP — these are organic/textured, not flat graphics
BACKDROP_WIDTHS = {"1x": 900, "2x": 1800}  # sky / distant
MIST_WIDTHS = {"1x": 700, "2x": 1400}  # smaller: mist is a soft, low-detail layer
MIST_QUALITY = 68
BACKDROP_QUALITY = 82
EDGE_CROP_FRAC = 0.03  # sky/distant: fraction cropped off the watermark corner
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
    border = np.concatenate(
        [im_rgb[0, :, :], im_rgb[-1, :, :], im_rgb[:, 0, :], im_rgb[:, -1, :]]
    )
    return border.mean(axis=0)


def _flood_fill_background_mask(im_rgb: np.ndarray, threshold: float) -> np.ndarray:
    """True = background. Seeds from every border pixel that already looks
    like background, then grows through any 4-connected neighbor within
    `threshold` of the sampled background color — so an interior pixel
    that merely resembles the backdrop color is never removed unless a
    continuous path of matching pixels actually connects it to the
    border."""
    bg_color = _background_color(im_rgb)
    dist = np.linalg.norm(im_rgb.astype(np.float32) - bg_color, axis=-1)
    candidate = dist < threshold

    mask = np.zeros_like(candidate)
    mask[0, :] = candidate[0, :]
    mask[-1, :] = candidate[-1, :]
    mask[:, 0] = candidate[:, 0]
    mask[:, -1] = candidate[:, -1]

    while True:
        grown = mask.copy()
        grown[1:, :] |= mask[:-1, :] & candidate[1:, :]
        grown[:-1, :] |= mask[1:, :] & candidate[:-1, :]
        grown[:, 1:] |= mask[:, :-1] & candidate[:, 1:]
        grown[:, :-1] |= mask[:, 1:] & candidate[:, :-1]
        if np.array_equal(grown, mask):
            return mask
        mask = grown


def chroma_key(src_path: Path, threshold: float = BG_THRESHOLD) -> Image.Image:
    full = Image.open(src_path).convert("RGB")
    w, h = full.size
    scale = MASK_WORK_SIZE / max(w, h)
    small = full.resize((max(1, round(w * scale)), max(1, round(h * scale))), Image.BILINEAR)
    bg_mask_small = _flood_fill_background_mask(np.asarray(small), threshold)

    # Upscaling the binary mask with BILINEAR gives a naturally anti-
    # aliased edge; a small Gaussian blur on top softens it further so the
    # cutout doesn't look stair-stepped at full resolution.
    alpha_small = (~bg_mask_small * 255).astype(np.uint8)
    alpha = Image.fromarray(alpha_small, mode="L").resize((w, h), Image.BILINEAR)
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=1.2))

    rgba = full.convert("RGBA")
    rgba.putalpha(alpha)
    return rgba


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


def export_fragment(im: Image.Image, out_dir: Path, name: str) -> dict:
    sizes = {}
    aspect = im.height / im.width
    for density, target_w in FRAGMENT_WIDTHS.items():
        target_h = max(1, round(target_w * aspect))
        resized = resize_rgba(im, (target_w, target_h))
        path = out_dir / f"{name}-{density}.webp"
        resized.save(path, "WEBP", quality=FRAGMENT_QUALITY, method=6)
        sizes[density] = path.stat().st_size
    return sizes


def process_mist(src_path: Path, out_dir: Path, name: str) -> dict:
    luminance = np.asarray(Image.open(src_path).convert("L")).astype(np.float32)
    floor, ceil = np.percentile(luminance, [5, 99])
    alpha = np.clip((luminance - floor) / max(1.0, ceil - floor), 0.0, 1.0) * 255
    alpha_img = Image.fromarray(alpha.astype(np.uint8), mode="L")

    white = Image.new("RGBA", alpha_img.size, (255, 255, 255, 255))
    white.putalpha(alpha_img)

    sizes = {}
    w, h = white.size
    for density, target_w in MIST_WIDTHS.items():
        target_h = max(1, round(target_w * h / w))
        resized = resize_rgba(white, (target_w, target_h))
        path = out_dir / f"{name}-{density}.webp"
        resized.save(path, "WEBP", quality=MIST_QUALITY, method=6)
        sizes[density] = path.stat().st_size
    return sizes


def process_backdrop(src_path: Path, out_dir: Path, name: str, edge_frac: float = EDGE_CROP_FRAC) -> dict:
    """Sky / distant: crop the watermark corner off, scale back up to the
    working size so the layer's framing doesn't shift, export at both
    densities."""
    im = Image.open(src_path).convert("RGB")
    w, h = im.size
    cropped = im.crop((0, 0, round(w * (1 - edge_frac)), round(h * (1 - edge_frac))))
    cropped = cropped.resize((w, h), Image.LANCZOS)

    sizes = {}
    for density, target_w in BACKDROP_WIDTHS.items():
        target_h = max(1, round(target_w * h / w))
        resized = cropped.resize((target_w, target_h), Image.LANCZOS)
        path = out_dir / f"{name}-{density}.webp"
        resized.save(path, "WEBP", quality=BACKDROP_QUALITY, method=6)
        sizes[density] = path.stat().st_size
    return sizes, cropped


def build_poster(sky: Image.Image, distant: Image.Image, mist_paths: list[Path], out_dir: Path) -> int:
    """Flattened full-scene composite for the no-JS / reduced-motion
    fallback — a representative static arrangement, not pixel-identical to
    HeroScene.tsx's live CSS layout (built before Part B's exact
    positioning exists); revisited if the two diverge noticeably."""
    canvas_h = round(POSTER_WIDTH * POSTER_ASPECT)
    base = sky.convert("RGBA").resize((POSTER_WIDTH, canvas_h), Image.LANCZOS)

    distant_layer = distant.convert("RGBA").resize((POSTER_WIDTH, canvas_h), Image.LANCZOS)
    distant_layer.putalpha(160)
    base.alpha_composite(distant_layer)

    for mist_src in mist_paths:
        mist_rgba = process_mist_image(mist_src)
        mist_resized = resize_rgba(mist_rgba, (POSTER_WIDTH, canvas_h))
        r, g, b, a = mist_resized.split()
        a = a.point(lambda v: int(v * 0.35))
        mist_resized = Image.merge("RGBA", (r, g, b, a))
        base.alpha_composite(mist_resized)

    path = out_dir / "poster.webp"
    base.convert("RGB").save(path, "WEBP", quality=82, method=6)
    return path.stat().st_size


def process_mist_image(src_path: Path) -> Image.Image:
    luminance = np.asarray(Image.open(src_path).convert("L")).astype(np.float32)
    floor, ceil = np.percentile(luminance, [5, 99])
    alpha = np.clip((luminance - floor) / max(1.0, ceil - floor), 0.0, 1.0) * 255
    alpha_img = Image.fromarray(alpha.astype(np.uint8), mode="L")
    white = Image.new("RGBA", alpha_img.size, (255, 255, 255, 255))
    white.putalpha(alpha_img)
    return white


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--out", default=DEFAULT_OUT, type=Path)
    args = parser.parse_args()

    src_dir: Path = args.source.expanduser()
    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    report = Report([])
    total_bytes = 0

    report.add(f"source: {src_dir}")
    report.add(f"out:    {out_dir}\n")

    report.add("-- fragments (chroma key + trim) --")
    for name, src_name in FRAGMENT_SRC.items():
        rgba = chroma_key(src_dir / src_name)
        rgba = trim_to_content(rgba)
        ok = corner_is_clean(rgba)
        sizes = export_fragment(rgba, out_dir, name)
        total_bytes += sum(sizes.values())
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

    report.add("\n-- backdrops (edge crop, watermark removed) --")
    sky_sizes, sky_cropped = process_backdrop(src_dir / SKY_SRC, out_dir, "sky")
    total_bytes += sum(sky_sizes.values())
    report.add(f"  sky        <- {SKY_SRC:16s} 1x={sky_sizes['1x']}B 2x={sky_sizes['2x']}B")
    distant_sizes, distant_cropped = process_backdrop(src_dir / DISTANT_SRC, out_dir, "distant")
    total_bytes += sum(distant_sizes.values())
    report.add(f"  distant    <- {DISTANT_SRC:16s} 1x={distant_sizes['1x']}B 2x={distant_sizes['2x']}B")

    report.add("\n-- poster (flattened fallback) --")
    mist_paths = [src_dir / s for s in MIST_SRC]
    poster_bytes = build_poster(sky_cropped, distant_cropped, mist_paths[:2], out_dir)
    total_bytes += poster_bytes
    report.add(f"  poster.webp  {poster_bytes}B")

    report.add(f"\nTOTAL hero/ weight: {total_bytes / 1_000_000:.2f} MB (budget: 1.5 MB target, 3 MB cap)")
    if total_bytes > 3_000_000:
        report.add("  !! OVER the 3 MB cap — revisit sizes/quality before committing")
    elif total_bytes > 1_500_000:
        report.add("  (over the 1.5 MB target, within the 3 MB cap)")


if __name__ == "__main__":
    main()
