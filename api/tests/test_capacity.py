from app.checks.capacity import (
    capacity_limit_t,
    certified_t_fy_to_date,
    check_c1,
    fy_start_month,
    months_elapsed_in_fy,
)


def test_fy_start_month_for_month_in_second_half():
    assert fy_start_month("2026-01") == "2025-04"


def test_fy_start_month_for_month_in_first_half():
    assert fy_start_month("2025-07") == "2025-04"


def test_months_elapsed_april_is_one():
    assert months_elapsed_in_fy("2025-04") == 1


def test_months_elapsed_march_is_twelve():
    assert months_elapsed_in_fy("2026-03") == 12


def test_certified_t_fy_to_date_sums_within_fy_only():
    certificates = [
        {"period_month": "2025-04", "quantity_t": 10.0},
        {"period_month": "2026-01", "quantity_t": 20.0},
        {"period_month": "2024-12", "quantity_t": 999.0},  # previous FY, excluded
    ]
    assert certified_t_fy_to_date(certificates, "2026-01") == 30.0


def test_capacity_limit_t_scales_linearly():
    assert capacity_limit_t(1200.0, 6) == 600.0


def test_check_c1_passes_within_capacity():
    certs = [{"period_month": "2026-03", "quantity_t": 1000.0}]
    result = check_c1("PWP-01", certs, capacity_t_per_year=1200.0, as_of_month="2026-03")
    assert result.status == "pass"
    assert result.affected_tonnes == 0.0


def test_check_c1_fails_above_capacity():
    # F1: certified 30% above capacity for the full FY.
    certs = [{"period_month": "2026-03", "quantity_t": 1560.0}]
    result = check_c1("PWP-05", certs, capacity_t_per_year=1200.0, as_of_month="2026-03")
    assert result.status == "fail"
    assert result.affected_tonnes == 360.0
