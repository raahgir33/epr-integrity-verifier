from app.models.agent import HypothesisConclusion, HypothesisRevision, Objection


def test_hypothesis_conclusion_defaults():
    conclusion = HypothesisConclusion(
        certificate_batch="2026-01", status="supported", explanation="ok"
    )
    assert conclusion.evidence_ids == []


def test_objection_defaults_and_independent_lists():
    a = Objection(finding_type="x", effect="raises_concern", explanation="a")
    b = Objection(finding_type="y", effect="raises_concern", explanation="b")
    a.cited_shipment_ids.append("SHP-1")
    assert b.cited_shipment_ids == []
    assert b.evidence_ids == []


def test_hypothesis_revision_fields():
    revision = HypothesisRevision(objection_index=0, accepted=True, explanation="confirmed")
    assert revision.objection_index == 0
    assert revision.accepted is True
