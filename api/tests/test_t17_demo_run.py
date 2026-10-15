"""T17: the live demo run's repeatability and its two failure modes.

Unlike tests/test_run_certificate_batch.py, whose fake BigQuery only
mirrors the `runs` table, the fake store here really applies every load
and delete — so a second run reads exactly what the first one wrote.
That is the whole point: the claim under test is that running the same
batch three times leaves identical assessments, check_results, shipments
and alerts, which is only meaningful if the writes actually accumulate.

Shipment matching, the checks and the scorer all run for real against
synthesised extracted_facts; only Gemini (extraction, the agent loop, the
memo) is faked.
"""

import datetime
import json

import pytest

from app.admin import reset_demo
from app.events import run_processor

SEED = 42
FACTS_SOURCE = "extracted"
PID = "PWP-03"
BATCH_ID = "BATCH-PWP-03-001"
DEMO_DOC_IDS = [
    f"{PID}-DEMO-INBOUND_INVOICE-001",
    f"{PID}-DEMO-EWAY_BILL-001",
    f"{PID}-DEMO-WEIGHBRIDGE_SLIP-001",
]
DEMO_SHIPMENT_ID = f"{PID}-DEMO-SHP-001"

_PROCESSOR_ROW = {
    "processor_id": PID,
    "name": "Vishwamitri Plastics Recycling Co.",
    "type": "recycler",
    "capacity_t_per_year": 172.8,
    "permitted_categories": ["I"],
    "consent_no": "CTO/GJ/770487",
    "consent_valid_from": datetime.date(2022, 4, 1),
    "consent_valid_to": datetime.date(2028, 3, 31),
    "registration_no": "EPR-REG/GJ/216739",
}

# One ordinary trio (126.72 t, Feb 2026) plus the demo trio (8.45 t
# invoiced / 8.49 t weighed, Mar 2026) — the real BATCH-PWP-03-001
# figures.
_TRIOS = [
    (
        "003",
        "004",
        "005",
        "ARPL/25-26/0001",
        "MP29AB7951",
        "126.72",
        "1,26,720",
        "10/02/2026",
        "10-02-2026 09:10",
        "15-02-2026 23:59",
        "11-02-2026 11:05",
        None,
    ),
    (
        None,
        None,
        None,
        "DEMO/25-26/0001",
        "MP54AB4100",
        "8.45",
        "8,490",
        "18/03/2026",
        "18-03-2026 09:10",
        "23-03-2026 23:59",
        "19-03-2026 11:05",
        "माल नहीं उतारा",
    ),
]


def _documents_and_facts() -> tuple[list[dict], list[dict]]:
    docs: list[dict] = []
    facts: list[dict] = []

    def add(doc_id: str, doc_type: str, fields: dict) -> None:
        docs.append(
            {
                "doc_id": doc_id,
                "processor_id": PID,
                "doc_type": doc_type,
                "gcs_path": f"seed-42/{doc_id}",
            }
        )
        for name, value in fields.items():
            facts.append(
                {
                    "doc_id": doc_id,
                    "processor_id": PID,
                    "field_name": name,
                    "printed_value": value,
                }
            )

    for (
        inv_n,
        eway_n,
        wb_n,
        inv_no,
        vehicle,
        qty_t,
        net_kg,
        inv_date,
        gen,
        until,
        in_t,
        remark,
    ) in _TRIOS:
        is_demo = inv_n is None
        prefix = f"{PID}-DEMO" if is_demo else PID
        inv_id = f"{prefix}-INBOUND_INVOICE-{'001' if is_demo else inv_n}"
        eway_id = f"{prefix}-EWAY_BILL-{'001' if is_demo else eway_n}"
        wb_id = f"{prefix}-WEIGHBRIDGE_SLIP-{'001' if is_demo else wb_n}"
        add(
            inv_id,
            "inbound_invoice",
            {
                "invoice_no": inv_no,
                "supplier_gstin": "08XZHIF1607H4ZC",
                "quantity_t": qty_t,
                "date": inv_date,
                "hsn": "3915",
            },
        )
        add(
            eway_id,
            "eway_bill",
            {
                "invoice_no": inv_no,
                "from_gstin": "08XZHIF1607H4ZC",
                "ewb_no": "649484225646" if not is_demo else "649484332271",
                "vehicle_no": vehicle,
                "generated_at": gen,
                "valid_until": until,
                "distance_km": "935.0",
            },
        )
        add(
            wb_id,
            "weighbridge_slip",
            {
                "vehicle_no": vehicle,
                "in_time": in_t,
                "net_kg": net_kg,
                "ticket_no": f"GJ-WB-5333-{'00011' if not is_demo else '00099'}",
                **({"remarks": remark} if remark else {}),
            },
        )
    return docs, facts


class _Finding:
    """The shape app/events/run_processor.py's _classified_findings reads."""

    finding_type = "Goods Not Unloaded"
    effect = "raises_concern"
    cited_shipment_ids = (DEMO_SHIPMENT_ID,)
    evidence_ids = tuple(DEMO_DOC_IDS)
    explanation = (
        "The weighbridge slip carries the handwritten remark 'माल नहीं उतारा' "
        "(goods not unloaded), so this shipment's tonnes are not verifiable."
    )


class _FakeGeminiClient:
    def flush_call_log(self):
        return []


class _FakeMemoDoc:
    def model_dump_json(self) -> str:
        return '{"subject": "fake"}'


def _run_row(run_id: str, snapshot_before: dict) -> dict:
    now = datetime.datetime(2026, 4, 1, tzinfo=datetime.UTC)
    return {
        "run_id": run_id,
        "batch_id": BATCH_ID,
        "processor_id": PID,
        "seed": SEED,
        "facts_source": FACTS_SOURCE,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "stage_timestamps_json": "{}",
        "error_message": None,
        "snapshot_before_json": json.dumps(snapshot_before),
        "alert_id": None,
    }


@pytest.fixture
def store(monkeypatch):
    """A fake BigQuery that honours loads and deletes, so writes persist
    across runs within one test."""
    docs, facts = _documents_and_facts()
    db: dict[str, list[dict]] = {
        "runs": [],
        "demo_batches": [
            {
                "batch_id": BATCH_ID,
                "processor_id": PID,
                "period_month": "2026-03",
                "quantity_t": 8.45,
                "pushes_over_verifiable": False,
                "extra_document_ids": list(DEMO_DOC_IDS),
            }
        ],
        "processors": [dict(_PROCESSOR_ROW)],
        "documents": docs,
        # The demo trio's facts are absent until the run extracts them,
        # exactly as load_demo_extra_docs.py leaves things.
        "extracted_facts": [f for f in facts if "-DEMO-" not in f["doc_id"]],
        "shipments": [],
        "certificates": [
            {
                "certificate_id": "EXISTING",
                "processor_id": PID,
                "brand_id": None,
                "category": "I",
                "quantity_t": 126.72,
                "period_month": "2026-02",
                "generation_date": datetime.date(2026, 2, 28),
            }
        ],
        "outputs": [],
        "energy_monthly": [],
        "site_assessments": [],
        "check_results": [],
        "assessments": [],
        "agent_runs": [],
        "memos": [],
        "alerts": [],
        "llm_calls": [],
    }
    demo_facts = [f for f in facts if "-DEMO-" in f["doc_id"]]

    # BigQuery hands TIMESTAMP columns back as datetimes and DATE columns
    # as dates, never as the ISO strings the writer passed in. The fake
    # has to do the same or it hides exactly the class of bug
    # _row_timestamp_to_iso exists to handle.
    _TS_COLUMNS = {
        "eway_generated_at",
        "eway_valid_until",
        "weighbridge_in_time",
        "created_at",
        "updated_at",
    }
    _DATE_COLUMNS = {"generation_date", "consent_valid_from", "consent_valid_to"}

    def _rehydrate(row: dict) -> dict:
        out = dict(row)
        for key, value in out.items():
            if not isinstance(value, str):
                continue
            if key in _TS_COLUMNS:
                out[key] = datetime.datetime.fromisoformat(value)
            elif key in _DATE_COLUMNS:
                out[key] = datetime.date.fromisoformat(value)
        return out

    def fetch_rows(client, table, columns, seed, processor_id=None, facts_source=None):
        rows = db.get(table, [])
        if processor_id is not None:
            rows = [r for r in rows if r.get("processor_id") == processor_id]
        if facts_source is not None:
            rows = [r for r in rows if r.get("facts_source", facts_source) == facts_source]
        return [_rehydrate(r) for r in rows]

    def load_rows(client, table, rows):
        for row in rows:
            json.dumps(row, default=str)
        db.setdefault(table, []).extend(dict(r) for r in rows)
        return len(rows)

    def delete_by_run_id(client, table, run_id):
        db[table] = [r for r in db.get(table, []) if r.get("run_id") != run_id]

    def delete_by_ids(client, table, id_column, ids):
        db[table] = [r for r in db.get(table, []) if r.get(id_column) not in set(ids)]

    def delete_by_processor(table):
        def inner(client, seed, facts_source, processor_id, stage=None):
            db[table] = [
                r
                for r in db.get(table, [])
                if not (
                    r.get("processor_id") == processor_id
                    and (stage is None or r.get("stage") == stage)
                )
            ]

        return inner

    monkeypatch.setattr(run_processor.bq, "get_client", lambda: object())
    monkeypatch.setattr(run_processor.bq, "fetch_rows", fetch_rows)
    monkeypatch.setattr(run_processor.bq, "load_rows", load_rows)
    monkeypatch.setattr(run_processor.bq, "delete_by_run_id", delete_by_run_id)
    monkeypatch.setattr(run_processor.bq, "delete_by_ids", delete_by_ids)
    monkeypatch.setattr(
        run_processor.bq, "delete_shipments_by_processor", delete_by_processor("shipments")
    )
    monkeypatch.setattr(
        run_processor.bq, "delete_check_results_by_processor", delete_by_processor("check_results")
    )
    monkeypatch.setattr(
        run_processor.bq, "delete_agent_runs_by_processor", delete_by_processor("agent_runs")
    )
    monkeypatch.setattr(run_processor.bq, "delete_memos_by_processor", delete_by_processor("memos"))
    monkeypatch.setattr(
        run_processor.bq,
        "delete_assessments_by_processor_and_stage",
        delete_by_processor("assessments"),
    )

    monkeypatch.setattr(run_processor.gcs, "get_client", lambda: object())
    monkeypatch.setattr(run_processor, "GeminiClient", _FakeGeminiClient)

    def fake_extract_all(llm, gcs_client, bucket, new_docs, purpose_prefix=""):
        by_doc: dict[str, dict] = {}
        for f in demo_facts:
            by_doc.setdefault(f["doc_id"], {})[f["field_name"]] = f["printed_value"]
        return [
            {
                "doc_id": d["doc_id"],
                "processor_id": PID,
                "doc_type": d["doc_type"],
                "status": "ok",
                "facts": by_doc.get(d["doc_id"], {}),
            }
            for d in new_docs
        ]

    monkeypatch.setattr(run_processor, "extract_all", fake_extract_all)
    monkeypatch.setattr(
        run_processor,
        "facts_to_field_rows",
        lambda facts_dict: [
            {"field_name": k, "printed_value": v, "confidence": 1.0, "page": 1}
            for k, v in facts_dict.items()
        ],
    )

    loop_result = {
        "deductible_findings": [_Finding()],
        "systemic_findings": [],
        "no_evidence_findings": [],
        "concurs_with_check_findings": [],
        "review_flag_findings": [],
        "excluded_shipment_ids": frozenset({DEMO_SHIPMENT_ID}),
        "agent_status": "ok",
    }
    monkeypatch.setattr(
        run_processor,
        "run_agent_loop_with_retry",
        lambda *a, **kw: (loop_result, [{"attempt": 1, "trail": [], "agent_status": "ok"}]),
    )
    monkeypatch.setattr(
        run_processor.memo,
        "build_memo_context",
        lambda **kwargs: {"doc_type": "clarification_memo"},
    )
    monkeypatch.setattr(
        run_processor.memo, "generate_clarification_memo", lambda ctx, llm: (_FakeMemoDoc(), "ok")
    )
    monkeypatch.setattr(run_processor.cache, "invalidate", lambda key=None: None)
    monkeypatch.setattr(run_processor.cache, "preload", lambda seed, fs: None)
    return db


def _outcome(db: dict) -> dict:
    """Everything the acceptance criteria compare, with the per-run
    timestamps and ids that are expected to differ stripped out."""

    def strip(rows, drop):
        return sorted(
            ({k: v for k, v in r.items() if k not in drop} for r in rows),
            key=lambda r: json.dumps(r, sort_keys=True, default=str),
        )

    return {
        "assessments": strip(db["assessments"], {"computed_at"}),
        "check_results": strip(db["check_results"], set()),
        "shipments": strip(db["shipments"], set()),
        # One alert row per run is by design (it is keyed on run_id, and
        # /alerts is a feed), so only this run's own alert is compared.
        "alert": strip(db["alerts"][-1:], {"alert_id", "run_id", "created_at"}),
    }


def _execute(db: dict, run_id: str, snapshot_before: dict) -> None:
    db["runs"].append(_run_row(run_id, snapshot_before))
    run_processor.run_certificate_batch(run_id)


def _live_snapshot_before(db: dict) -> dict:
    """What app/main.py used to build before T17: the current full
    assessment plus the current findings."""
    full = next(
        (a for a in db["assessments"] if a["stage"] == "full" and a["processor_id"] == PID), None
    )
    return {
        "risk_band": full["risk_band"] if full else None,
        "findings": (
            [{"cited_shipment_ids": [DEMO_SHIPMENT_ID], "classification": "deductible"}]
            if full
            else []
        ),
    }


# The baseline C7-lite pins: PWP-03's bundled pre-demo snapshot says Low
# with no findings.
PRE_DEMO = {"risk_band": "Low", "findings": []}


def test_the_demo_run_tells_the_planted_remark_story(store):
    _execute(store, "RUN-1", PRE_DEMO)

    run = store["runs"][0]
    assert run["status"] == "done", run["error_message"]

    # The demo trio matched, in its own id namespace, leaving the
    # dossier's own shipment numbering alone.
    ids = sorted(s["shipment_id"] for s in store["shipments"])
    assert ids == [DEMO_SHIPMENT_ID, f"{PID}-EXT-SHP-001"]
    demo = next(s for s in store["shipments"] if s["shipment_id"] == DEMO_SHIPMENT_ID)
    assert demo["match_status"] == "matched"
    assert demo["month"] == "2026-03"
    assert demo["weighbridge_net_t"] == pytest.approx(8.49)

    by_stage = {a["stage"]: a for a in store["assessments"]}
    # Checks alone see a fully backed dossier...
    assert by_stage["checks_only"]["unverifiable_t"] == pytest.approx(0.0)
    assert by_stage["checks_only"]["risk_band"] == "Low"
    # ...and the agents' handwritten-remark finding deducts the batch.
    assert by_stage["full"]["unverifiable_t"] == pytest.approx(8.45)
    assert by_stage["full"]["risk_band"] == "Medium"

    alert = store["alerts"][0]
    assert (alert["risk_band_before"], alert["risk_band_after"]) == ("Low", "Medium")
    assert "माल नहीं उतारा" in alert["new_finding_summary"]


def test_three_runs_of_the_same_batch_are_identical(store):
    """The acceptance criterion: a second and a third click produce the
    same outcome as the first."""
    outcomes = []
    for i in (1, 2, 3):
        _execute(store, f"RUN-{i}", PRE_DEMO)
        assert store["runs"][-1]["status"] == "done", store["runs"][-1]["error_message"]
        outcomes.append(_outcome(store))

    assert outcomes[1] == outcomes[0]
    assert outcomes[2] == outcomes[0]

    # Each run still raises its own alert, with the same transition.
    assert len(store["alerts"]) == 3
    for alert in store["alerts"]:
        assert (alert["risk_band_before"], alert["risk_band_after"]) == ("Low", "Medium")
        assert alert["new_finding_summary"]

    # And nothing accumulated in the state tables: every write is
    # delete-then-load on a key the run owns.
    assert len(store["shipments"]) == 2
    assert len(store["assessments"]) == 2
    assert len(store["memos"]) == 1
    demo_certs = [c for c in store["certificates"] if c["certificate_id"].startswith("CERT-DEMO")]
    assert len(demo_certs) == 1


def test_without_the_pinned_baseline_the_second_run_raises_no_alert(store):
    """Why C7-lite exists. Reading "before" from live state makes run 2
    compare Medium against the Medium run 1 wrote, with the same finding
    already present — so _decide_alert correctly reports nothing, and the
    panel tells a judge on their second click that nothing happened."""
    _execute(store, "RUN-1", _live_snapshot_before(store))
    assert len(store["alerts"]) == 1

    _execute(store, "RUN-2", _live_snapshot_before(store))
    assert len(store["alerts"]) == 1, "run 2 should have produced no new alert"


def test_a_missing_demo_document_fails_the_run_loudly(store):
    """C3. The documents rows are the one thing only a developer-run
    script can create; when a reset had removed them the run used to
    sail through its extraction stage having read nothing."""
    store["documents"] = [d for d in store["documents"] if "-DEMO-" not in d["doc_id"]]

    _execute(store, "RUN-1", PRE_DEMO)

    run = store["runs"][0]
    assert run["status"] == "failed"
    assert "not registered in the documents table" in run["error_message"]
    for doc_id in DEMO_DOC_IDS:
        assert doc_id in run["error_message"]
    assert "load_demo_extra_docs.py" in run["error_message"]
    # It failed before writing any assessment, so the previous run's
    # figures are left standing rather than half-replaced.
    assert store["assessments"] == []


def test_alert_id_reaches_the_run_row_before_reasoning_finishes(store, monkeypatch):
    """C4 (API half). The alerts row was written before
    finish_stage("reasoning") all along, but the run row did not carry
    alert_id until finish(), so GET /runs reported no alert for the whole
    drafting_memo stage and cache re-warm — 39s on the 2026-10-15 run."""
    seen: list[tuple[str, str | None, bool]] = []
    original = run_processor._write_run

    def spy(bq_client, run_row):
        stages = json.loads(run_row.get("stage_timestamps_json") or "{}")
        seen.append((run_row["status"], run_row.get("alert_id"), "reasoning" in stages))
        return original(bq_client, run_row)

    monkeypatch.setattr(run_processor, "_write_run", spy)
    _execute(store, "RUN-1", PRE_DEMO)

    # The first write that records the reasoning timestamp must already
    # carry the alert_id.
    first_with_reasoning = next(w for w in seen if w[2])
    assert first_with_reasoning[1] is not None

    # And no write ever reports a reasoning timestamp with no alert_id.
    assert all(alert_id is not None for _status, alert_id, has_reasoning in seen if has_reasoning)


def test_snapshot_before_from_bundle_reads_the_pre_demo_band(monkeypatch):
    """C7-lite's source of truth: PWP-03's bundled snapshot, not live
    state. Findings reconstruction is stubbed — it needs a BigQuery-backed
    context, and what matters here is that the band comes off the
    stage="full" row of the bundled file."""
    monkeypatch.setattr(reset_demo.cache, "findings_from_trail", lambda *a, **kw: [])

    before = reset_demo.snapshot_before_from_bundle(SEED, FACTS_SOURCE, PID)

    assert before == {"risk_band": "Low", "findings": []}


def test_snapshot_before_from_bundle_is_none_without_a_snapshot():
    assert reset_demo.snapshot_before_from_bundle(SEED, FACTS_SOURCE, "PWP-02") is None
