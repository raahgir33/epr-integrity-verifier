"""C8 — site plausibility (docs/DATA_SPEC.md §4). Earth Engine: Open
Buildings v3 footprint near the registered coordinates, and a Sentinel-2
thumbnail with the buildings and the detection radius painted onto it
server-side (not drawn client-side later).

Pure core / thin I/O shell, same split as app/checks/: `_aggregate_footprint`
and `check_c8` are pure and hand-tested; `query_site_buildings` and
`build_site_thumbnail` call real Earth Engine and are not unit-tested —
run only by the developer (scripts/run_pipeline.py --stage site).
"""

import json

import ee
import requests
from google.cloud import storage

from app.checks import params
from app.config import settings
from app.models.checks import CheckResult
from app.store import gcs

_OPEN_BUILDINGS_COLLECTION = "GOOGLE/Research/open-buildings/v3/polygons"
_SENTINEL_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
_CLOUD_FILTER_MAX_PCT = 20

# ~1 km box via buffer().bounds() — metres-based, correct at any
# latitude, unlike a fixed degree offset (internal engineering notes §9's known trap).
_THUMBNAIL_BOX_RADIUS_M = 500
_THUMBNAIL_PX = 512
_THUMBNAIL_CRS = "EPSG:3857"
_OUTLINE_WIDTH_PX = 2
_BUILDING_OUTLINE_COLOR = "yellow"
_RADIUS_OUTLINE_COLOR = "red"

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# Attribution strings for /method (T12) — not duplicated into every
# site_assessments row, since they never vary per processor.
SENTINEL_ATTRIBUTION = "Contains modified Copernicus Sentinel data (2023)"
OPEN_BUILDINGS_ATTRIBUTION = "Open Buildings v3, Google Research — CC BY 4.0"

_ee_initialized = False


def _ensure_ee_initialized() -> None:
    global _ee_initialized
    if not _ee_initialized:
        ee.Initialize(project=settings.gcp_project)
        _ee_initialized = True


# ---------- pure core ----------


def _aggregate_footprint(buildings: list[dict], min_confidence: float) -> tuple[float, int]:
    """buildings: [{"confidence": float, "area_m2": float, "ring": [...]}, ...].
    Returns (total_footprint_m2, building_count) after the confidence
    filter — the only filtering C8 applies; the ring itself isn't used
    here, only kept for the row's polygons_json evidence."""
    qualifying = [b for b in buildings if (b.get("confidence") or 0.0) >= min_confidence]
    total_footprint_m2 = sum(b.get("area_m2") or 0.0 for b in qualifying)
    return total_footprint_m2, len(qualifying)


def check_c8(
    processor_id: str, capacity_t_per_year: float, total_footprint_m2: float
) -> CheckResult:
    """docs/DATA_SPEC.md §4: claimed capacity per m² of footprint <=
    MAX_TPA_PER_M2; no buildings at all is treated as a strong signal
    (explanation says so), but still status="warn" — C8 is soft severity,
    same pass/warn vocabulary as C2b/C7, never "fail"."""
    if total_footprint_m2 <= 0:
        return CheckResult(
            check_id="C8",
            status="warn",
            severity="soft",
            measured=None,
            threshold=params.MAX_TPA_PER_M2,
            affected_tonnes=None,
            evidence_ids=[],
            explanation=(
                f"{processor_id}: no building footprint detected within "
                f"{params.SITE_RADIUS_M} m of the registered coordinates — a "
                "strong signal of a ghost site."
            ),
        )

    capacity_per_m2 = capacity_t_per_year / total_footprint_m2
    status = "pass" if capacity_per_m2 <= params.MAX_TPA_PER_M2 else "warn"
    return CheckResult(
        check_id="C8",
        status=status,
        severity="soft",
        measured=capacity_per_m2,
        threshold=params.MAX_TPA_PER_M2,
        affected_tonnes=None,
        evidence_ids=[],
        explanation=(
            f"{processor_id}: claimed capacity is {capacity_per_m2:.2f} t per m² of "
            f"building footprint (ceiling {params.MAX_TPA_PER_M2} t/m²)."
        ),
    )


def site_assessment_to_check_result(row: dict) -> CheckResult:
    """Converts a site_assessments row back into a CheckResult so
    agents/scorer.py's soft-signal bump can consume C8 (T9 wires this in;
    the bump logic itself, apply_soft_signal_bump, already existed from T8
    and already looked for check_id "C8" — it just had nothing to find)."""
    return CheckResult(
        check_id="C8",
        status=row["status"],
        severity=row.get("severity") or "soft",
        measured=row.get("measured"),
        threshold=row.get("threshold"),
        affected_tonnes=None,
        evidence_ids=[row["thumbnail_gcs_path"]] if row.get("thumbnail_gcs_path") else [],
        explanation=row.get("explanation") or "",
    )


# ---------- Earth Engine I/O — never run by the agent, developer only ----------


def query_site_buildings(lat: float, lon: float, radius_m: float) -> list[dict]:
    """GOOGLE/Research/open-buildings/v3/polygons within radius_m of
    (lat, lon). Returns every building regardless of confidence —
    _aggregate_footprint applies the MIN_BUILDING_CONFIDENCE filter."""
    _ensure_ee_initialized()
    region = ee.Geometry.Point([lon, lat]).buffer(radius_m)
    buildings = ee.FeatureCollection(_OPEN_BUILDINGS_COLLECTION).filterBounds(region)
    info = buildings.getInfo()

    results = []
    for feature in info.get("features", []):
        props = feature.get("properties", {})
        geometry = feature.get("geometry") or {}
        ring = []
        if geometry.get("type") == "Polygon":
            coordinates = geometry.get("coordinates") or [[]]
            ring = coordinates[0]
        results.append(
            {
                "confidence": props.get("confidence"),
                "area_m2": props.get("area_in_meters"),
                "ring": ring,
            }
        )
    return results


def build_site_thumbnail(lat: float, lon: float) -> tuple[bytes, dict]:
    """Sentinel-2 median composite (params.S2_DATE_START/END, matching
    Open Buildings v3's own imagery vintage) over a metres-based ~1 km
    box, with the Open Buildings outlines and the SITE_RADIUS_M detection
    circle painted onto it server-side. Returns (png_bytes,
    {"bbox": (w, s, e, n), "crs": ...}) — bbox in WGS84 degrees
    (independent of the export's own pixel crs), read back from the
    region geometry, not computed from a naive degree offset.
    """
    _ensure_ee_initialized()
    center = ee.Geometry.Point([lon, lat])
    region = center.buffer(_THUMBNAIL_BOX_RADIUS_M).bounds()

    s2 = (
        ee.ImageCollection(_SENTINEL_COLLECTION)
        .filterBounds(region)
        .filterDate(params.S2_DATE_START, params.S2_DATE_END)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", _CLOUD_FILTER_MAX_PCT))
        .median()
    )
    rgb = s2.visualize(bands=["B4", "B3", "B2"], min=0, max=3000)

    buildings = (
        ee.FeatureCollection(_OPEN_BUILDINGS_COLLECTION)
        .filterBounds(region)
        .filter(ee.Filter.gte("confidence", params.MIN_BUILDING_CONFIDENCE))
    )
    building_outline = ee.Image().byte().paint(buildings, 1, _OUTLINE_WIDTH_PX)
    building_vis = building_outline.visualize(
        min=0, max=1, palette=[_BUILDING_OUTLINE_COLOR]
    ).updateMask(building_outline)

    radius_fc = ee.FeatureCollection([ee.Feature(center.buffer(params.SITE_RADIUS_M))])
    radius_outline = ee.Image().byte().paint(radius_fc, 1, _OUTLINE_WIDTH_PX)
    radius_vis = radius_outline.visualize(min=0, max=1, palette=[_RADIUS_OUTLINE_COLOR]).updateMask(
        radius_outline
    )

    composite = rgb.blend(building_vis).blend(radius_vis)
    thumb_url = composite.getThumbURL(
        {"region": region, "dimensions": _THUMBNAIL_PX, "format": "png", "crs": _THUMBNAIL_CRS}
    )

    # getThumbURL links expire (internal engineering notes §9) — fetch the bytes now, never
    # persist the URL itself.
    response = requests.get(thumb_url, timeout=30)
    if response.status_code != 200:
        raise RuntimeError(
            f"Earth Engine thumbnail fetch failed: HTTP {response.status_code} ({lat}, {lon})"
        )
    data = response.content
    if not data.startswith(_PNG_MAGIC):
        raise RuntimeError(
            f"Earth Engine thumbnail response was not a PNG for ({lat}, {lon}) — "
            f"got {len(data)} bytes starting {data[:16]!r}"
        )

    bbox_coords = region.getInfo()["coordinates"][0]
    lons = [c[0] for c in bbox_coords]
    lats = [c[1] for c in bbox_coords]
    bbox = (min(lons), min(lats), max(lons), max(lats))

    return data, {"bbox": bbox, "crs": _THUMBNAIL_CRS}


def run_site_assessment(processor: dict) -> tuple[dict, bytes]:
    """processor: {processor_id, capacity_t_per_year, lat, lon}. Returns
    (row, thumbnail_png_bytes) — row matches the site_assessments table
    minus seed/computed_at/thumbnail_gcs_path, which the caller fills in
    after uploading the bytes to Cloud Storage."""
    processor_id = processor["processor_id"]
    lat, lon = processor["lat"], processor["lon"]

    buildings = query_site_buildings(lat, lon, params.SITE_RADIUS_M)
    total_footprint_m2, building_count = _aggregate_footprint(
        buildings, params.MIN_BUILDING_CONFIDENCE
    )
    result = check_c8(processor_id, processor["capacity_t_per_year"], total_footprint_m2)
    thumbnail_bytes, thumb_meta = build_site_thumbnail(lat, lon)
    w, s, e, n = thumb_meta["bbox"]

    row = {
        "processor_id": processor_id,
        "status": result.status,
        "severity": result.severity,
        "measured": result.measured,
        "threshold": result.threshold,
        "building_count": building_count,
        "total_footprint_m2": total_footprint_m2,
        "polygons_json": json.dumps(
            [
                {
                    "confidence": b.get("confidence"),
                    "area_m2": b.get("area_m2"),
                    "ring": b.get("ring"),
                }
                for b in buildings
            ]
        ),
        "thumb_bbox_w": w,
        "thumb_bbox_s": s,
        "thumb_bbox_e": e,
        "thumb_bbox_n": n,
        "thumb_crs": thumb_meta["crs"],
        "explanation": result.explanation,
    }
    return row, thumbnail_bytes


def upload_thumbnail(
    gcs_client: storage.Client, bucket: str, seed: int, processor_id: str, data: bytes
) -> str:
    """Uploads thumbnail bytes and returns the GCS blob path used."""
    blob_path = f"seed-{seed}/site/{processor_id}.png"
    gcs.upload_bytes(gcs_client, bucket, blob_path, data, content_type="image/png")
    return blob_path
