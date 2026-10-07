"""T9 follow-up: does the F5 ghost-site coordinate (data/synthetic/
site_coordinates.json) actually follow whichever processor the catalog
assigns F5 to, or could a future edit to one file silently drift from the
other? scripts/dossier_gen/world.py's _PROCESSOR_CATALOG and
site_coordinates.json are two separately-maintained files joined only by
processor_id — nothing enforces they stay in sync except convention.

Confirmed by reading code (docs/PROGRESS.md has the full narrative):
_PROCESSOR_CATALOG is a literal, hardcoded list with no `rng` involvement,
so which processor_id carries F5 is identical for every seed, including
the held-out seed 7 (never generated here). This test makes that
guarantee an active regression check instead of a one-time code read: if
anyone ever moves F5 to a different processor_id in the catalog without
also moving the ghost-site coordinate in site_coordinates.json, this
fails, across every dev seed.

Seeds 1-20, excluding 7 (held-out test set, never generated or inspected,
directly or indirectly).
"""

import json

import pytest

from scripts.dossier_gen.rng import new_rng
from scripts.dossier_gen.world import SITE_COORDINATES_PATH, build_processors

DEV_SEEDS = [s for s in range(1, 21) if s != 7]


def _ghost_site_processor_id(site_coordinates: dict) -> str:
    """The processor_id whose site_coordinates.json note identifies it as
    the F5 ghost site — found by content, not hardcoded to "PWP-09", so
    this test checks the actual coupling rather than just restating it."""
    candidates = [pid for pid, site in site_coordinates.items() if "F5" in site.get("note", "")]
    assert len(candidates) == 1, (
        f"expected exactly one site_coordinates.json entry mentioning F5, got {candidates}"
    )
    return candidates[0]


@pytest.mark.parametrize("seed", DEV_SEEDS)
def test_f5_processor_matches_ghost_site_coordinate(seed):
    processors = build_processors(new_rng(seed))
    site_coordinates = json.loads(SITE_COORDINATES_PATH.read_text(encoding="utf-8"))

    f5_processors = [p for p in processors if "F5" in p.issue_types]
    assert len(f5_processors) == 1, (
        f"seed {seed}: expected exactly one F5 processor, got {len(f5_processors)}"
    )
    f5_processor = f5_processors[0]

    ghost_site_processor_id = _ghost_site_processor_id(site_coordinates)
    assert f5_processor.processor_id == ghost_site_processor_id, (
        f"seed {seed}: F5 is assigned to {f5_processor.processor_id!r}, but the ghost-site "
        f"coordinate in site_coordinates.json belongs to {ghost_site_processor_id!r} — "
        "they've drifted apart"
    )

    ghost_site = site_coordinates[ghost_site_processor_id]
    assert f5_processor.lat == ghost_site["lat"]
    assert f5_processor.lon == ghost_site["lon"]
