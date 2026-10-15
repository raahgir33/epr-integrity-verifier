"""Shared demo-reset core (T13.8). The actual BigQuery delete-then-restore
mechanics (docs/BUILD_PLAN.md T13's accept criterion) live in run_reset()
below — one source of truth for two callers that each supply its input
from whichever source they can actually reach:

- api/scripts/reset_demo.py (developer CLI) reads demo_batches.json and
  pre_demo_snapshot/*.json from data/synthetic/ on disk.
- POST /admin/reset-demo (app/main.py, this task) runs inside the
  deployed Cloud Run container, where data/ and scripts/ never ship
  (api/Dockerfile only COPY app ./app) — run_reset_live() below reads
  demo_batches from the live BigQuery table instead (already there since
  T13 — same source GET /demo-batches reads via cache.get_demo_batches),
  and the three tiny (112 KB total) pre_demo_snapshot/{pid}.json files
  from api/app/admin/data/pre_demo_snapshot/, bundled copies that ship
  inside the image because they live under app/.

  Those bundled copies are frozen at this task's commit. If the demo
  dataset is ever regenerated (scripts/generate_dossiers.py /
  scripts/snapshot_demo_processors.py re-run) before submission, re-copy
  data/synthetic/seed-42/pre_demo_snapshot/*.json here and redeploy, or
  the live reset endpoint restores stale rows.
"""

import json
from pathlib import Path

from app.store import bq, cache

DEMO_TOUCHED_PROCESSOR_IDS = ["PWP-01", "PWP-03", "PWP-05"]

_BUNDLED_SNAPSHOT_DIR = Path(__file__).resolve().parent / "data" / "pre_demo_snapshot"


def run_reset(
    bq_client: object, seed: int, demo_batches: list[dict], snapshots: dict[str, dict]
) -> list[str]:
    """demo_batches: {batch_id, processor_id, extra_document_ids, ...}
    dicts (from demo_batches.json, or a live `demo_batches` BigQuery row
    set — same shape either way). snapshots: processor_id -> its
    pre_demo_snapshot dict; a processor in DEMO_TOUCHED_PROCESSOR_IDS with
    no entry is skipped, same as the original script. Delete-then-load
    throughout, so calling this twice converges to the same state
    (idempotent). Returns the processor_ids actually restored."""
    bq.delete_by_seed(bq_client, "runs", seed)
    bq.delete_by_seed(bq_client, "alerts", seed)

    cert_ids = [f"CERT-DEMO-{b['batch_id']}" for b in demo_batches]
    bq.delete_by_ids(bq_client, "certificates", "certificate_id", cert_ids)

    extra_doc_ids = [doc_id for b in demo_batches for doc_id in b.get("extra_document_ids") or []]
    if extra_doc_ids:
        # The `documents` rows are deliberately NOT deleted. They are
        # static registry rows that only scripts/load_demo_extra_docs.py
        # (developer-run) can create, and nothing ever puts them back —
        # so deleting them here permanently removed the demo's own
        # evidence after the first reset, and every run since added a
        # certificate with no document trail to match it. Diagnosed
        # 2026-10-15: GET /processors/PWP-03/documents listed zero
        # PWP-03-DEMO-* rows, so the live path's extraction stage read
        # nothing and the planted-remark finding could not be raised.
        #
        # `extracted_facts` IS deleted, which is the intended reset:
        # DocumentListItem.extraction_status goes back to
        # "not_extracted", so the next live run really does run Gemini
        # over these documents rather than reusing a previous run's
        # facts.
        bq.delete_by_ids(bq_client, "extracted_facts", "doc_id", extra_doc_ids)
        bq.delete_shipments_by_document_ids(bq_client, seed, extra_doc_ids)

    restored = []
    for processor_id in DEMO_TOUCHED_PROCESSOR_IDS:
        snapshot = snapshots.get(processor_id)
        if snapshot is None:
            continue
        facts_source = snapshot["facts_source"]

        bq.delete_check_results_by_processor(bq_client, seed, facts_source, processor_id)
        bq.load_rows(bq_client, "check_results", snapshot["check_results"])

        for stage in {row["stage"] for row in snapshot["assessments"]}:
            bq.delete_assessments_by_processor_and_stage(
                bq_client, seed, facts_source, processor_id, stage
            )
        bq.load_rows(bq_client, "assessments", snapshot["assessments"])

        bq.delete_agent_runs_by_processor(bq_client, seed, facts_source, processor_id)
        bq.load_rows(bq_client, "agent_runs", snapshot["agent_runs"])

        bq.delete_memos_by_processor(bq_client, seed, facts_source, processor_id)
        bq.load_rows(bq_client, "memos", snapshot["memos"])

        restored.append(processor_id)

    return restored


def load_bundled_snapshots() -> dict[str, dict]:
    snapshots = {}
    for processor_id in DEMO_TOUCHED_PROCESSOR_IDS:
        path = _BUNDLED_SNAPSHOT_DIR / f"{processor_id}.json"
        if path.exists():
            snapshots[processor_id] = json.loads(path.read_text(encoding="utf-8"))
    return snapshots


def read_bundled_snapshot(processor_id: str) -> dict | None:
    path = _BUNDLED_SNAPSHOT_DIR / f"{processor_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def snapshot_before_from_bundle(seed: int, facts_source: str, processor_id: str) -> dict | None:
    """The alert decision's "before" state, taken from this processor's
    bundled pre-demo snapshot instead of whatever the last run left in
    BigQuery. None when no snapshot is bundled for it, so the caller
    (app/main.py's POST /demo/certificate-batch) falls back to live
    state.

    Why: app/events/run_processor.py's _decide_alert fires only when the
    band rose or a qualifying finding is new. Reading "before" from live
    state makes the first run of the day fire Low -> High and every
    later run fire nothing at all, because run 2 compares High against
    the High run 1 just wrote and sees the same findings. Judges click
    more than once. Anchoring "before" to the pre-demo snapshot makes
    every run report the same real transition, without restoring any
    table mid-run.

    risk_band comes from the snapshot's stage="full" assessment — the
    same stage the badge reads everywhere. findings are reconstructed
    from the snapshot's own agent_runs trail through
    cache.findings_from_trail, the same code path the live read uses, so
    the signature set compared against is built exactly the way the
    "after" set is."""
    snapshot = read_bundled_snapshot(processor_id)
    if snapshot is None:
        return None
    full = next((a for a in snapshot.get("assessments", []) if a.get("stage") == "full"), None)
    trail = cache.latest_attempt_trail(snapshot.get("agent_runs", []))
    findings = cache.findings_from_trail(seed, facts_source, processor_id, trail)
    return {
        "risk_band": full["risk_band"] if full else None,
        "findings": [
            {"cited_shipment_ids": f["cited_shipment_ids"], "classification": f["classification"]}
            for f in findings
        ],
    }


def run_reset_live(seed: int) -> list[str]:
    """POST /admin/reset-demo's entrypoint — demo_batches from BigQuery,
    snapshots from the bundled copies. Does not touch the read cache;
    app/main.py's route calls cache.invalidate()+cache.preload() itself
    right after, so a failed reset never leaves a half-warmed cache."""
    bq_client = bq.get_client()
    demo_batches = cache.get_demo_batches(seed)
    snapshots = load_bundled_snapshots()
    return run_reset(bq_client, seed, demo_batches, snapshots)
