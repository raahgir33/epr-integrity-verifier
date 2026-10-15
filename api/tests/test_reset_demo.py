"""Tests for scripts/reset_demo.py's run_reset — against a fake
app.store.bq module and a tmp_path-based fake data/synthetic/seed-<seed>/
tree. No real BigQuery call.
"""

import json

import pytest

from scripts import reset_demo


@pytest.fixture
def fake_seed_dir(tmp_path, monkeypatch):
    seed_dir = tmp_path / "data" / "synthetic" / "seed-42"
    (seed_dir / "pre_demo_snapshot").mkdir(parents=True)
    monkeypatch.setattr(reset_demo, "REPO_ROOT", tmp_path)

    demo_batches = [
        {
            "batch_id": "BATCH-PWP-01-001",
            "processor_id": "PWP-01",
            "extra_document_ids": [
                "PWP-01-DEMO-INBOUND_INVOICE-001",
                "PWP-01-DEMO-EWAY_BILL-001",
                "PWP-01-DEMO-WEIGHBRIDGE_SLIP-001",
            ],
        },
        {"batch_id": "BATCH-PWP-05-001", "processor_id": "PWP-05", "extra_document_ids": []},
    ]
    (seed_dir / "demo_batches.json").write_text(json.dumps(demo_batches), encoding="utf-8")

    for pid in ("PWP-01", "PWP-03", "PWP-05"):
        snapshot = {
            "seed": 42,
            "facts_source": "extracted",
            "processor_id": pid,
            "check_results": [{"processor_id": pid, "check_id": "C1"}],
            "assessments": [
                {"processor_id": pid, "stage": "checks_only"},
                {"processor_id": pid, "stage": "full"},
            ],
            "agent_runs": [{"processor_id": pid, "step_index": 0}],
            "memos": [{"processor_id": pid, "lang": "en"}],
        }
        (seed_dir / "pre_demo_snapshot" / f"{pid}.json").write_text(
            json.dumps(snapshot), encoding="utf-8"
        )

    return seed_dir


@pytest.fixture
def fake_bq(monkeypatch):
    calls = {"deletes": [], "loads": []}

    def fake_delete_by_seed(client, table, seed):
        calls["deletes"].append(("by_seed", table))

    def fake_delete_by_ids(client, table, id_column, ids):
        calls["deletes"].append(("by_ids", table, tuple(ids)))

    monkeypatch.setattr(reset_demo.bq, "get_client", lambda: object())
    monkeypatch.setattr(reset_demo.bq, "delete_by_seed", fake_delete_by_seed)
    monkeypatch.setattr(reset_demo.bq, "delete_by_ids", fake_delete_by_ids)
    monkeypatch.setattr(
        reset_demo.bq,
        "delete_shipments_by_document_ids",
        lambda client, seed, doc_ids: calls["deletes"].append(("shipments_by_doc", tuple(doc_ids))),
    )
    monkeypatch.setattr(
        reset_demo.bq,
        "delete_check_results_by_processor",
        lambda client, seed, fs, pid: calls["deletes"].append(("check_results", pid)),
    )
    monkeypatch.setattr(
        reset_demo.bq,
        "delete_assessments_by_processor_and_stage",
        lambda client, seed, fs, pid, stage: calls["deletes"].append(("assessments", pid, stage)),
    )
    monkeypatch.setattr(
        reset_demo.bq,
        "delete_agent_runs_by_processor",
        lambda client, seed, fs, pid: calls["deletes"].append(("agent_runs", pid)),
    )
    monkeypatch.setattr(
        reset_demo.bq,
        "delete_memos_by_processor",
        lambda client, seed, fs, pid: calls["deletes"].append(("memos", pid)),
    )
    monkeypatch.setattr(
        reset_demo.bq,
        "load_rows",
        lambda client, table, rows: calls["loads"].append((table, len(rows))),
    )
    return calls


def test_run_reset_deletes_runs_and_alerts_entirely(fake_seed_dir, fake_bq):
    reset_demo.run_reset(42)

    assert ("by_seed", "runs") in fake_bq["deletes"]
    assert ("by_seed", "alerts") in fake_bq["deletes"]


def test_run_reset_deletes_demo_batch_certificates_by_id(fake_seed_dir, fake_bq):
    reset_demo.run_reset(42)

    cert_deletes = [c for c in fake_bq["deletes"] if c[0] == "by_ids" and c[1] == "certificates"]
    assert len(cert_deletes) == 1
    assert set(cert_deletes[0][2]) == {"CERT-DEMO-BATCH-PWP-01-001", "CERT-DEMO-BATCH-PWP-05-001"}


def test_run_reset_keeps_the_demo_extra_documents(fake_seed_dir, fake_bq):
    """T17: the `documents` rows must survive a reset.

    Only scripts/load_demo_extra_docs.py (developer-run, hits Cloud
    Storage) can create them, and nothing else ever puts them back — so
    deleting them here silently disarmed the demo after its first reset:
    the live path's extraction stage found nothing to read and the new
    certificate had no shipment to match."""
    reset_demo.run_reset(42)

    doc_deletes = [c for c in fake_bq["deletes"] if c[0] == "by_ids" and c[1] == "documents"]
    assert doc_deletes == []


def test_run_reset_deletes_demo_extracted_facts_and_shipments(fake_seed_dir, fake_bq):
    """extracted_facts still goes, so extraction_status returns to
    "not_extracted" and the next run really re-reads the documents; and
    the shipment those documents produced goes with it, or it would
    outlive its own deleted certificate — a month showing verified
    inbound tonnes against zero certified."""
    reset_demo.run_reset(42)

    facts_deletes = [
        c for c in fake_bq["deletes"] if c[0] == "by_ids" and c[1] == "extracted_facts"
    ]
    shipment_deletes = [c for c in fake_bq["deletes"] if c[0] == "shipments_by_doc"]
    assert len(facts_deletes) == 1
    assert len(facts_deletes[0][2]) == 3
    assert len(shipment_deletes) == 1
    assert shipment_deletes[0][1] == facts_deletes[0][2]


def test_run_reset_restores_every_touched_processor_from_its_snapshot(fake_seed_dir, fake_bq):
    reset_demo.run_reset(42)

    for pid in ("PWP-01", "PWP-03", "PWP-05"):
        assert ("check_results", pid) in fake_bq["deletes"]
        assert ("agent_runs", pid) in fake_bq["deletes"]
        assert ("memos", pid) in fake_bq["deletes"]
        assert ("assessments", pid, "checks_only") in fake_bq["deletes"]
        assert ("assessments", pid, "full") in fake_bq["deletes"]

    loaded_tables = [table for table, _count in fake_bq["loads"]]
    assert loaded_tables.count("check_results") == 3
    assert loaded_tables.count("agent_runs") == 3
    assert loaded_tables.count("memos") == 3
    assert loaded_tables.count("assessments") == 3


def test_run_reset_skips_a_processor_with_no_snapshot(fake_seed_dir, fake_bq):
    (fake_seed_dir / "pre_demo_snapshot" / "PWP-03.json").unlink()

    reset_demo.run_reset(42)

    assert ("check_results", "PWP-03") not in fake_bq["deletes"]
    assert ("check_results", "PWP-01") in fake_bq["deletes"]
    assert ("check_results", "PWP-05") in fake_bq["deletes"]
