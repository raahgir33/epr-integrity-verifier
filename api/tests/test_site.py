"""Tests for app/geo/site.py's pure functions only — _aggregate_footprint,
check_c8, site_assessment_to_check_result. query_site_buildings and
build_site_thumbnail call real Earth Engine and are not unit-tested; they
are run only by the developer (scripts/run_pipeline.py --stage site).
"""

from app.checks import params
from app.geo.site import _aggregate_footprint, check_c8, site_assessment_to_check_result


def _building(**overrides) -> dict:
    base = {"confidence": 0.9, "area_m2": 100.0, "ring": [[0.0, 0.0]]}
    base.update(overrides)
    return base


def test_aggregate_footprint_empty_list():
    total, count = _aggregate_footprint([], params.MIN_BUILDING_CONFIDENCE)
    assert total == 0.0
    assert count == 0


def test_aggregate_footprint_filters_below_confidence():
    buildings = [
        _building(confidence=0.9, area_m2=100.0),
        _building(confidence=0.5, area_m2=200.0),  # below threshold, excluded
    ]
    total, count = _aggregate_footprint(buildings, min_confidence=0.75)
    assert total == 100.0
    assert count == 1


def test_aggregate_footprint_sums_qualifying_area():
    buildings = [_building(area_m2=50.0), _building(area_m2=75.5)]
    total, count = _aggregate_footprint(buildings, min_confidence=0.75)
    assert total == 125.5
    assert count == 2


def test_aggregate_footprint_handles_missing_fields():
    buildings = [{"confidence": None, "area_m2": None, "ring": []}]
    total, count = _aggregate_footprint(buildings, min_confidence=0.75)
    assert total == 0.0
    assert count == 0


def test_check_c8_passes_within_ceiling():
    # 1000 t / 200 m^2 = 5 t/m^2, under the 10 t/m^2 ceiling.
    result = check_c8("PWP-01", capacity_t_per_year=1000.0, total_footprint_m2=200.0)
    assert result.status == "pass"
    assert result.severity == "soft"
    assert result.measured == 5.0
    assert result.threshold == params.MAX_TPA_PER_M2


def test_check_c8_warns_above_ceiling():
    # 1000 t / 20 m^2 = 50 t/m^2, well above the 10 t/m^2 ceiling.
    result = check_c8("PWP-01", capacity_t_per_year=1000.0, total_footprint_m2=20.0)
    assert result.status == "warn"
    assert result.severity == "soft"
    assert result.measured == 50.0


def test_check_c8_warns_on_zero_footprint():
    # F5: ghost site, no buildings detected at all.
    result = check_c8("PWP-09", capacity_t_per_year=20000.0, total_footprint_m2=0.0)
    assert result.status == "warn"
    assert result.severity == "soft"
    assert result.measured is None
    assert "ghost site" in result.explanation


def test_site_assessment_to_check_result_round_trips():
    row = {
        "status": "warn",
        "severity": "soft",
        "measured": None,
        "threshold": params.MAX_TPA_PER_M2,
        "thumbnail_gcs_path": "seed-42/site/PWP-09.png",
        "explanation": "no building footprint detected",
    }
    result = site_assessment_to_check_result(row)
    assert result.check_id == "C8"
    assert result.status == "warn"
    assert result.severity == "soft"
    assert result.evidence_ids == ["seed-42/site/PWP-09.png"]
    assert result.explanation == "no building footprint detected"


def test_site_assessment_to_check_result_handles_missing_optional_fields():
    row = {"status": "pass"}
    result = site_assessment_to_check_result(row)
    assert result.check_id == "C8"
    assert result.status == "pass"
    assert result.severity == "soft"
    assert result.evidence_ids == []
    assert result.explanation == ""
