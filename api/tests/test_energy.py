from app.checks.energy import check_c7, month_passes_c7


def test_within_band_passes():
    # 400 kWh/t, within [150, 1200].
    assert month_passes_c7(kwh=40000.0, certified_t_month=100.0) is True


def test_near_zero_consumption_fails():
    # F7: near-zero electricity for a month with real certified tonnage.
    assert month_passes_c7(kwh=20.0, certified_t_month=100.0) is False


def test_zero_certified_tonnage_is_skipped():
    # H4: planned shutdown month — nothing to divide by, not a flag.
    assert month_passes_c7(kwh=20.0, certified_t_month=0.0) is None


def test_check_c7_passes_when_all_months_within_band():
    energy_monthly = [{"doc_id": "D1", "month": "2025-04", "kwh": 40000.0}]
    result = check_c7("PWP-01", energy_monthly, {"2025-04": 100.0})
    assert result.status == "pass"
    assert result.severity == "soft"


def test_check_c7_warns_on_implausible_month():
    energy_monthly = [{"doc_id": "D1", "month": "2025-07", "kwh": 20.0}]
    result = check_c7("PWP-07", energy_monthly, {"2025-07": 100.0})
    assert result.status == "warn"
    assert result.severity == "soft"
    assert result.affected_tonnes == 100.0
    assert result.evidence_ids == ["D1"]


def test_check_c7_skips_shutdown_month_without_flagging():
    energy_monthly = [{"doc_id": "D1", "month": "2025-12", "kwh": 20.0}]
    result = check_c7("PWP-04", energy_monthly, {"2025-12": 0.0})
    assert result.status == "not_evaluable"


def test_check_c7_mixed_months_only_failing_counted():
    energy_monthly = [
        {"doc_id": "D-OK", "month": "2025-04", "kwh": 40000.0},
        {"doc_id": "D-BAD", "month": "2025-07", "kwh": 20.0},
    ]
    certified_t_by_month = {"2025-04": 100.0, "2025-07": 100.0}
    result = check_c7("PWP-07", energy_monthly, certified_t_by_month)
    assert result.status == "warn"
    assert result.affected_tonnes == 100.0
    assert result.evidence_ids == ["D-BAD"]
