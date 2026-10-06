"""Smoke test: Earth Engine — Open Buildings count near a test coordinate.

Run: uv run python scripts/smoke/smoke_ee.py

If this fails after `gcloud auth application-default login`, run
`earthengine authenticate` (from the earthengine-api package) and retry —
see docs/GCP_SETUP.md section 6.
"""

import sys

import ee

from app.config import settings

# An arbitrary point in India, used only to confirm the Open Buildings
# dataset is queryable from this project/region — not a processor site.
TEST_LAT = 19.07
TEST_LON = 72.87
RADIUS_M = 500


def main() -> int:
    print("--- smoke_ee: Open Buildings count near a test coordinate ---")
    try:
        ee.Initialize(project=settings.gcp_project)

        point = ee.Geometry.Point([TEST_LON, TEST_LAT])
        region = point.buffer(RADIUS_M)
        buildings = ee.FeatureCollection("GOOGLE/Research/open-buildings/v3/polygons").filterBounds(
            region
        )

        count = buildings.size().getInfo()
        print(f"building count within {RADIUS_M} m of ({TEST_LAT}, {TEST_LON}): {count}")

        print("smoke_ee: PASS")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"smoke_ee: FAIL — {exc!r}")
        print(
            "If this is an authentication error, run `earthengine authenticate` "
            "and retry (docs/GCP_SETUP.md section 6)."
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
