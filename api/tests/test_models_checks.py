from app.models.checks import CheckResult


def test_check_result_defaults():
    result = CheckResult(check_id="C1", status="pass", severity="hard", explanation="ok")
    assert result.evidence_ids == []
    assert result.measured is None


def test_check_result_evidence_ids_are_independent_between_instances():
    a = CheckResult(check_id="C1", status="fail", severity="hard", explanation="a")
    b = CheckResult(check_id="C2", status="fail", severity="hard", explanation="b")
    a.evidence_ids.append("DOC-1")
    assert b.evidence_ids == []
