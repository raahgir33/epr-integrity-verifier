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
        bq.delete_by_ids(bq_client, "documents", "doc_id", extra_doc_ids)
        bq.delete_by_ids(bq_client, "extracted_facts", "doc_id", extra_doc_ids)

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


def run_reset_live(seed: int) -> list[str]:
    """POST /admin/reset-demo's entrypoint — demo_batches from BigQuery,
    snapshots from the bundled copies. Does not touch the read cache;
    app/main.py's route calls cache.invalidate()+cache.preload() itself
    right after, so a failed reset never leaves a half-warmed cache."""
    bq_client = bq.get_client()
    demo_batches = cache.get_demo_batches(seed)
    snapshots = load_bundled_snapshots()
    return run_reset(bq_client, seed, demo_batches, snapshots)
