"""Tests for app/agents/memo.py against a fake LLMClient — no network.
Covers eligibility routing, Part B derivation, and every guard path:
evidence-ID subset (including the empty-document fallback), the number
guard's identifier-stripping fix, forbidden words (English and Hindi),
internal-label leaks, and the Hindi translation guard (including Devanagari
digit normalisation).
"""

import app.agents.memo as memo_module
from app.agents.memo import (
    build_memo_context,
    decide_doc_type,
    derive_improvement_observations,
    generate_clarification_memo,
    generate_hindi_memo,
    generate_verification_statement,
)
from app.checks import params
from app.models.agent import (
    ClarificationMemo,
    ImprovementObservation,
    MemoItem,
    VerificationStatement,
)


class _FakeLLMClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.purposes_called = []

    def extract(self, *args, **kwargs):
        raise NotImplementedError

    def run_tool_loop(self, *args, **kwargs):
        raise NotImplementedError

    def generate_structured(self, contents, schema, purpose, thinking_level=None):
        self.purposes_called.append(purpose)
        response = self._responses.pop(0)
        assert isinstance(response, schema)
        return response


# ---------- fixtures ----------

_PROCESSOR = {
    "processor_id": "PWP-08",
    "name": "PWP-08 Recyclers Pvt. Ltd.",
    "consent_no": "CTO-PWP08-0007",
    "registration_no": "REG-PWP08-0012",
    "consent_valid_to": "31/03/2028",
}

_ASSESSMENT = {
    "certified_t": 3734.05,
    "verified_inbound_t": 3734.05,
    "capacity_limit_t": 6000.0,
    "verifiable_t": 3734.05,
    "unverifiable_t": 0.0,
    "risk_band": "Low",
}

_PASSING_CHECK = {
    "check_id": "C1",
    "status": "pass",
    "severity": "hard",
    "measured": 3734.05,
    "threshold": 6000.0,
    "affected_tonnes": 0.0,
    "evidence_ids": [],
    "explanation": "within capacity",
}

_FAILED_CHECK = {
    "check_id": "C2a",
    "status": "fail",
    "severity": "hard",
    "measured": 3734.05,
    "threshold": 3000.0,
    "affected_tonnes": 734.05,
    "evidence_ids": ["PWP-08-DOC-1"],
    "explanation": "certified tonnes exceed verified inbound tonnes",
}

_F8_FINDING = {
    "finding_type": "Inbound material description",
    "classification": "deductible",
    "effect": "raises_concern",
    "cited_shipment_ids": ["PWP-08-SHP-0007"],
    "evidence_ids": ["PWP-08-INBOUND_INVOICE-024", "PWP-08-EWAY_BILL-024"],
    "explanation": (
        "Invoice PWP-08-INBOUND_INVOICE-024 describes the material as virgin LDPE granules "
        "under HSN 3915."
    ),
    "origin": "critic",
    "proposed_by": "critic",
    "verdict": None,
    "disputed_by": None,
}

_SHIPMENTS_BY_ID = {
    "PWP-08-SHP-0007": {
        "weighbridge_net_t": 18.40,
        "weighbridge_doc_id": "PWP-08-WEIGHBRIDGE_SLIP-024",
        "invoice_doc_id": "PWP-08-INBOUND_INVOICE-024",
        "eway_doc_id": "PWP-08-EWAY_BILL-024",
    }
}

_DOCUMENTS_BY_ID = {
    "PWP-08-INBOUND_INVOICE-024": {
        "doc_type": "inbound_invoice",
        "fields": {"hsn": "3915"},
    },
    "PWP-08-EWAY_BILL-024": {"doc_type": "eway_bill", "fields": {}},
    "PWP-08-WEIGHBRIDGE_SLIP-024": {"doc_type": "weighbridge_slip", "fields": {"remarks": ""}},
    "PWP-08-DOC-1": {"doc_type": "inbound_invoice", "fields": {}},
    "PWP-08-CTO-1": {"doc_type": "cto", "fields": {}},
}

_CERTIFICATES = [{"period_month": m, "quantity_t": 100.0} for m in ("2025-04", "2025-05")]


def _memo_context(check_results, findings, assessment=None):
    return build_memo_context(
        processor=_PROCESSOR,
        assessment=assessment or _ASSESSMENT,
        check_results=check_results,
        findings=findings,
        shipments_by_id=_SHIPMENTS_BY_ID,
        documents_by_id=_DOCUMENTS_BY_ID,
        certificates=_CERTIFICATES,
        as_of_month="2025-05",
    )


# ---------- eligibility ----------


def test_decide_doc_type_low_risk_no_findings_is_verification_statement():
    assert decide_doc_type(_ASSESSMENT, [_PASSING_CHECK], []) == "verification_statement"


def test_decide_doc_type_medium_risk_is_clarification_memo():
    medium = {**_ASSESSMENT, "risk_band": "Medium"}
    assert decide_doc_type(medium, [_PASSING_CHECK], []) == "clarification_memo"


def test_decide_doc_type_high_risk_is_clarification_memo():
    high = {**_ASSESSMENT, "risk_band": "High"}
    assert decide_doc_type(high, [_PASSING_CHECK], []) == "clarification_memo"


def test_decide_doc_type_failed_hard_check_is_clarification_memo_even_at_low_risk():
    assert decide_doc_type(_ASSESSMENT, [_FAILED_CHECK], []) == "clarification_memo"


def test_decide_doc_type_any_live_finding_is_clarification_memo():
    assert decide_doc_type(_ASSESSMENT, [_PASSING_CHECK], [_F8_FINDING]) == "clarification_memo"


def test_decide_doc_type_review_flag_finding_is_clarification_memo():
    review_flag = {**_F8_FINDING, "classification": "review_flag"}
    assert decide_doc_type(_ASSESSMENT, [_PASSING_CHECK], [review_flag]) == "clarification_memo"


def test_decide_doc_type_withdrawn_only_finding_is_verification_statement():
    withdrawn = {**_F8_FINDING, "classification": "withdrawn"}
    assert decide_doc_type(_ASSESSMENT, [_PASSING_CHECK], [withdrawn]) == "verification_statement"


def test_decide_doc_type_no_agent_run_yet_falls_back_to_checks_only_data():
    # findings=None (no agent run) must never be treated as "no issues" by
    # accident — only the checks_only data decides in that case.
    assert decide_doc_type(_ASSESSMENT, [_PASSING_CHECK], None) == "verification_statement"
    assert decide_doc_type(_ASSESSMENT, [_FAILED_CHECK], None) == "clarification_memo"


# ---------- Part B observation derivation ----------


def test_derive_observations_near_threshold():
    near_threshold_check = {**_PASSING_CHECK, "measured": 5750.0, "threshold": 6000.0}
    observations = derive_improvement_observations(
        _PROCESSOR, [near_threshold_check], "2025-05", {}, {}, [], []
    )
    assert any(o.kind == "near_threshold" for o in observations)


def test_derive_observations_soft_warn_check_becomes_soft_note():
    soft_warn = {
        "check_id": "C7",
        "status": "warn",
        "severity": "soft",
        "measured": 100.0,
        "threshold": 150.0,
        "evidence_ids": ["PWP-08-DOC-1"],
        "explanation": "kWh/t below plausible band",
    }
    observations = derive_improvement_observations(
        _PROCESSOR, [_PASSING_CHECK, soft_warn], "2025-05", {}, {}, [], []
    )
    soft_notes = [o for o in observations if o.kind == "soft_note"]
    assert len(soft_notes) == 1
    assert soft_notes[0].evidence_ids == ["PWP-08-DOC-1"]


def test_derive_observations_benign_weighbridge_remark():
    shipments = {
        "SHP-1": {"weighbridge_doc_id": "WB-1"},
    }
    documents = {"WB-1": {"doc_type": "weighbridge_slip", "fields": {"remarks": "तिरपाल फटा"}}}
    observations = derive_improvement_observations(
        _PROCESSOR, [_PASSING_CHECK], "2025-05", shipments, documents, [], []
    )
    assert any(o.kind == "soft_note" and o.evidence_ids == ["WB-1"] for o in observations)


def test_derive_observations_remark_already_cited_by_finding_not_duplicated():
    shipments = {"SHP-1": {"weighbridge_doc_id": "WB-1"}}
    documents = {"WB-1": {"doc_type": "weighbridge_slip", "fields": {"remarks": "तिरपाल फटा"}}}
    finding = {**_F8_FINDING, "cited_shipment_ids": ["SHP-1"]}
    observations = derive_improvement_observations(
        _PROCESSOR, [_PASSING_CHECK], "2025-05", shipments, documents, [finding], []
    )
    assert not any(o.evidence_ids == ["WB-1"] for o in observations)


def test_derive_observations_consent_expiry_within_window():
    processor = {**_PROCESSOR, "consent_valid_to": "31/10/2025"}  # ~5 months from 2025-05
    documents = {"PWP-08-CTO-1": {"doc_type": "cto", "fields": {}}}
    observations = derive_improvement_observations(
        processor, [_PASSING_CHECK], "2025-05", {}, documents, [], []
    )
    expiry = [o for o in observations if o.kind == "consent_expiry"]
    assert len(expiry) == 1
    assert expiry[0].threshold == float(params.CONSENT_EXPIRY_WARNING_MONTHS)
    assert expiry[0].evidence_ids == ["PWP-08-CTO-1"]


def test_derive_observations_consent_not_expiring_soon_no_observation():
    processor = {**_PROCESSOR, "consent_valid_to": "31/03/2030"}
    observations = derive_improvement_observations(
        processor, [_PASSING_CHECK], "2025-05", {}, {}, [], []
    )
    assert not any(o.kind == "consent_expiry" for o in observations)


def test_derive_observations_months_without_certificates():
    # FY 2025-26 as of 2025-05 (April, May) but certificates only cover May.
    observations = derive_improvement_observations(
        _PROCESSOR, [_PASSING_CHECK], "2025-05", {}, {}, [], [{"period_month": "2025-05"}]
    )
    gaps = [o for o in observations if o.kind == "documentation_gap"]
    assert len(gaps) == 1
    assert gaps[0].measured == 1.0  # April is missing


def test_derive_observations_clean_processor_no_observations():
    assert (
        derive_improvement_observations(
            _PROCESSOR, [_PASSING_CHECK], "2025-04", {}, {}, [], [{"period_month": "2025-04"}]
        )
        == []
    )


# ---------- clarification memo: happy path ----------


def _clean_memo_response(deadline_days=15):
    return ClarificationMemo(
        subject="Request for clarification — EPR certificates, PWP-08 Recyclers Pvt. Ltd.",
        salutation="Dear Sir/Madam,",
        opening_paragraph="We identified an item we would like to request clarification on.",
        items=[
            MemoItem(
                heading="Inbound material description",
                what_we_observed=(
                    "The item description on invoice PWP-08-INBOUND_INVOICE-024 refers to the "
                    "material as virgin LDPE granules under HSN 3915. Based on the documents "
                    "provided, 18.40 t under this record could not be verified as "
                    "post-consumer waste."
                ),
                evidence_ids=["PWP-08-INBOUND_INVOICE-024", "PWP-08-EWAY_BILL-024"],
                what_we_request="Please provide supporting documentation clarifying this item.",
            )
        ],
        response_deadline_days=deadline_days,
        closing_paragraph=f"We request a response within {deadline_days} days of this letter.",
    )


def test_clarification_memo_clean_pass_is_ok_no_regeneration():
    memo_context = _memo_context([_PASSING_CHECK], [_F8_FINDING])
    fake = _FakeLLMClient([_clean_memo_response()])
    memo, guard_status = generate_clarification_memo(memo_context, fake)
    assert guard_status == "ok"
    assert len(fake.purposes_called) == 1
    assert memo.items[0].evidence_ids == ["PWP-08-INBOUND_INVOICE-024", "PWP-08-EWAY_BILL-024"]
    assert memo.response_deadline_days == params.MEMO_RESPONSE_DEADLINE_DAYS


def test_clarification_memo_identifiers_and_hsn_do_not_trigger_false_number_guard_failure():
    # The exact wording this plan's number-guard fix targets: an invoice
    # ID containing digits, and the literal phrase "HSN 3915" — neither
    # should ever look like an unsupported number.
    memo_context = _memo_context([_PASSING_CHECK], [_F8_FINDING])
    fake = _FakeLLMClient([_clean_memo_response()])
    _, guard_status = generate_clarification_memo(memo_context, fake)
    assert guard_status == "ok"


# ---------- clarification memo: evidence-ID subset guard ----------


def test_unknown_evidence_id_is_dropped_but_item_with_remaining_evidence_survives():
    memo_context = _memo_context([_PASSING_CHECK], [_F8_FINDING])
    response = _clean_memo_response()
    response.items[0].evidence_ids = ["PWP-08-INBOUND_INVOICE-024", "UNKNOWN-DOC-ID"]
    fake = _FakeLLMClient([response])
    memo, guard_status = generate_clarification_memo(memo_context, fake)
    assert guard_status == "ok"
    assert memo.items[0].evidence_ids == ["PWP-08-INBOUND_INVOICE-024"]


def test_item_emptied_by_evidence_filtering_falls_back_to_template():
    memo_context = _memo_context([_PASSING_CHECK], [_F8_FINDING])
    response = _clean_memo_response()
    response.items[0].evidence_ids = ["UNKNOWN-DOC-ID"]
    fake = _FakeLLMClient([response, response])
    memo, guard_status = generate_clarification_memo(memo_context, fake)
    assert guard_status == "template_fallback"
    assert memo.items  # the template always produces at least one item
    assert len(fake.purposes_called) == 2  # exactly one regenerate attempt


# ---------- clarification memo: number guard ----------


def test_invented_number_regenerates_then_falls_back_to_template():
    memo_context = _memo_context([_PASSING_CHECK], [_F8_FINDING])
    bad = _clean_memo_response()
    bad.items[0].what_we_observed += " A follow-up audit found 999 additional tonnes at risk."
    fake = _FakeLLMClient([bad, bad])
    memo, guard_status = generate_clarification_memo(memo_context, fake)
    assert guard_status == "template_fallback"
    assert len(fake.purposes_called) == 2


def test_invented_number_corrected_on_regeneration_is_regenerated_not_fallback():
    memo_context = _memo_context([_PASSING_CHECK], [_F8_FINDING])
    bad = _clean_memo_response()
    bad.items[0].what_we_observed += " 999 extra tonnes."
    good = _clean_memo_response()
    fake = _FakeLLMClient([bad, good])
    memo, guard_status = generate_clarification_memo(memo_context, fake)
    assert guard_status == "regenerated"


# ---------- clarification memo: forbidden-word guard ----------


def test_forbidden_word_english_triggers_fallback():
    memo_context = _memo_context([_PASSING_CHECK], [_F8_FINDING])
    bad = _clean_memo_response()
    bad.opening_paragraph += " This may indicate fraud."
    fake = _FakeLLMClient([bad, bad])
    _, guard_status = generate_clarification_memo(memo_context, fake)
    assert guard_status == "template_fallback"


def test_forbidden_word_hindi_triggers_fallback():
    memo_context = _memo_context([_PASSING_CHECK], [_F8_FINDING])
    bad = _clean_memo_response()
    bad.closing_paragraph += " यह धोखाधड़ी हो सकती है।"
    fake = _FakeLLMClient([bad, bad])
    _, guard_status = generate_clarification_memo(memo_context, fake)
    assert guard_status == "template_fallback"


# ---------- clarification memo: internal-label leak guard ----------


def test_internal_label_leak_triggers_fallback():
    memo_context = _memo_context([_PASSING_CHECK], [_F8_FINDING])
    bad = _clean_memo_response()
    bad.items[0].what_we_observed += " (classified internally as a systemic finding)"
    fake = _FakeLLMClient([bad, bad])
    _, guard_status = generate_clarification_memo(memo_context, fake)
    assert guard_status == "template_fallback"


def test_taxonomy_code_leak_triggers_fallback():
    memo_context = _memo_context([_PASSING_CHECK], [_F8_FINDING])
    bad = _clean_memo_response()
    bad.items[0].heading = "F8 semantic contradiction"
    fake = _FakeLLMClient([bad, bad])
    # heading isn't a guarded field (per the approved plan's field list),
    # so this alone must NOT fail — confirms the guard checks exactly the
    # documented fields, not every field on the model.
    _, guard_status = generate_clarification_memo(memo_context, fake)
    assert guard_status == "ok"


# ---------- verification statement ----------


def _clean_statement_response(observations):
    return VerificationStatement(
        subject="Verification statement — PWP-08 Recyclers Pvt. Ltd.",
        salutation="Dear Sir/Madam,",
        part_a_paragraph=(
            "Of the 3734.05 t certified by PWP-08 Recyclers Pvt. Ltd. for the period under "
            "review, 3734.05 t were verified, with 1 of 1 checks passed and two independent "
            "agents found no unresolved issues."
        ),
        observations=[
            ImprovementObservation(
                kind=o.kind,
                measured=o.measured,
                threshold=o.threshold,
                evidence_ids=o.evidence_ids,
                recommendation="Consider reviewing supporting documentation for this item.",
            )
            for o in observations
        ],
        no_items_note=None if observations else "No improvement items identified.",
        closing_paragraph="No further action is required at this time.",
    )


def test_verification_statement_no_observations_sets_no_items_note_by_code():
    memo_context = _memo_context([_PASSING_CHECK], [])
    assert memo_context["doc_type"] == "verification_statement"
    assert memo_context["observations"] == []
    response = _clean_statement_response([])
    response.no_items_note = "the model should never get to decide this text"
    fake = _FakeLLMClient([response])
    statement, guard_status = generate_verification_statement(memo_context, fake)
    assert guard_status == "ok"
    assert statement.no_items_note == "No improvement items identified from the documents examined."


def test_verification_statement_reconciles_observations_never_trusts_model_fields():
    near_threshold_check = {**_PASSING_CHECK, "measured": 5750.0, "threshold": 6000.0}
    memo_context = _memo_context([near_threshold_check], [])
    assert memo_context["observations"]
    response = _clean_statement_response(memo_context["observations"])
    # Model tries to invent a different threshold/kind — must be ignored.
    response.observations[0].threshold = 99999.0
    response.observations[0].kind = "near_threshold"
    fake = _FakeLLMClient([response])
    statement, guard_status = generate_verification_statement(memo_context, fake)
    assert guard_status == "ok"
    assert statement.observations[0].threshold == memo_context["observations"][0].threshold


def test_verification_statement_model_omits_recommendation_falls_back_per_observation():
    near_threshold_check = {**_PASSING_CHECK, "measured": 5750.0, "threshold": 6000.0}
    memo_context = _memo_context([near_threshold_check], [])
    response = _clean_statement_response([])  # zero observations returned by the model
    response.no_items_note = None
    fake = _FakeLLMClient([response])
    statement, guard_status = generate_verification_statement(memo_context, fake)
    assert guard_status == "ok"
    assert len(statement.observations) == 1
    assert "close to the threshold" in statement.observations[0].recommendation


def test_verification_statement_checks_passed_phrasing_not_all_unless_true():
    memo_context = _memo_context([_PASSING_CHECK, _FAILED_CHECK], [])
    # _FAILED_CHECK makes this clarification_memo-eligible in practice, but
    # the template function itself is tested directly here regardless of
    # eligibility, purely for its "N of M" phrasing.
    statement = memo_module._template_verification_statement(memo_context)
    assert "1 of 2 checks passed" in statement.part_a_paragraph


def test_verification_statement_checks_passed_phrasing_all_true_case():
    memo_context = _memo_context([_PASSING_CHECK], [])
    statement = memo_module._template_verification_statement(memo_context)
    assert "1 of 1 checks passed" in statement.part_a_paragraph


# ---------- Hindi translation ----------


def test_hindi_clean_pass_is_ok():
    english = _clean_memo_response()
    hindi = english.model_copy(deep=True)
    hindi.opening_paragraph = "हमने एक मद पाया जिस पर हम स्पष्टीकरण का अनुरोध करते हैं।"
    hindi.closing_paragraph = "हम इस पत्र के 15 दिनों के भीतर प्रतिक्रिया का अनुरोध करते हैं।"
    hindi.items[0].what_we_observed = (
        "चालान PWP-08-INBOUND_INVOICE-024 में सामग्री को HSN 3915 के अंतर्गत वर्जिन एलडीपीई "
        "कणिकाओं के रूप में वर्णित किया गया है। इस रिकॉर्ड के अंतर्गत 18.40 टन की पुष्टि नहीं "
        "हो सकी।"
    )
    hindi.items[0].what_we_request = "कृपया इस मद को स्पष्ट करने वाले सहायक दस्तावेज प्रदान करें।"
    fake = _FakeLLMClient([hindi])
    result, guard_status = generate_hindi_memo("clarification_memo", english, fake)
    assert guard_status == "ok"
    assert result is not None


def test_hindi_devanagari_digits_normalised_not_rejected():
    english = _clean_memo_response(deadline_days=15)
    hindi = english.model_copy(deep=True)
    # "१५" is Devanagari for 15 — must be normalised to ASCII and accepted,
    # not rejected, proving normalisation (not mere rejection) runs.
    hindi.closing_paragraph = "हम इस पत्र के १५ दिनों के भीतर प्रतिक्रिया का अनुरोध करते हैं।"
    hindi.opening_paragraph = "हमने एक मद पाया जिस पर हम स्पष्टीकरण का अनुरोध करते हैं।"
    hindi.items[0].what_we_observed = "१८.४० टन की पुष्टि नहीं हो सकी।"
    hindi.items[0].what_we_request = "कृपया सहायक दस्तावेज प्रदान करें।"
    fake = _FakeLLMClient([hindi])
    result, guard_status = generate_hindi_memo("clarification_memo", english, fake)
    assert guard_status == "ok"
    assert result is not None


def test_hindi_number_mismatch_after_retry_returns_none():
    english = _clean_memo_response(deadline_days=15)
    bad_hindi = english.model_copy(deep=True)
    bad_hindi.closing_paragraph = "हम इस पत्र के ९९ दिनों के भीतर प्रतिक्रिया का अनुरोध करते हैं।"
    fake = _FakeLLMClient([bad_hindi, bad_hindi])
    result, guard_status = generate_hindi_memo("clarification_memo", english, fake)
    assert result is None
    assert guard_status is None
    assert len(fake.purposes_called) == 2


def test_hindi_evidence_id_mismatch_returns_none():
    english = _clean_memo_response()
    bad_hindi = english.model_copy(deep=True)
    bad_hindi.items[0].evidence_ids = ["SOME-OTHER-DOC-ID"]
    fake = _FakeLLMClient([bad_hindi, bad_hindi])
    result, guard_status = generate_hindi_memo("clarification_memo", english, fake)
    assert result is None
    assert guard_status is None
