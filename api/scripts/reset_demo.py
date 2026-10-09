"""Restores the pre-demo state for a seed's live event path (docs/
BUILD_PLAN.md T13's accept criterion). Deletes every runs/alerts row,
deletes the demo-batch certificates and the demo-extra documents/
extracted_facts rows, and restores check_results/assessments/agent_runs/
memos for every processor a demo batch can touch from the snapshot
scripts/snapshot_demo_processors.py took before the first live click.

Zero new Gemini calls, fast, fully deterministic — never re-runs checks/
agents/memo live. Safe to run as many times as the developer wants to
rehearse the demo again.

Run by the developer — never by the agent (hits real BigQuery).

Usage: uv run python scripts/reset_demo.py --seed 42
"""

import argparse
import json
from pathlib import Path

from app.store import bq

REPO_ROOT = Path(__file__).resolve().parents[2]

DEMO_TOUCHED_PROCESSOR_IDS = ["PWP-01", "PWP-03", "PWP-05"]


def run_reset(seed: int) -> None:
    """The restore logic itself, separated from main()'s argparse/CLI
    wrapper so tests/test_reset_demo.py can exercise it directly against
    a fake bq module, the same split scripts/run_pipeline.py's run_checks/
    run_agents/run_memo already use."""
    seed_dir = REPO_ROOT / "data" / "synthetic" / f"seed-{seed}"
    snapshot_dir = seed_dir / "pre_demo_snapshot"
    demo_batches = json.loads((seed_dir / "demo_batches.json").read_text(encoding="utf-8"))

    bq_client = bq.get_client()

    print("Deleting runs/alerts rows...")
    bq.delete_by_seed(bq_client, "runs", seed)
    bq.delete_by_seed(bq_client, "alerts", seed)

    cert_ids = [f"CERT-DEMO-{b['batch_id']}" for b in demo_batches]
    print(f"Deleting {len(cert_ids)} demo-batch certificate row(s)...")
    bq.delete_by_ids(bq_client, "certificates", "certificate_id", cert_ids)

    extra_doc_ids = [doc_id for b in demo_batches for doc_id in b.get("extra_document_ids") or []]
    if extra_doc_ids:
        print(f"Deleting {len(extra_doc_ids)} demo-extra documents/extracted_facts row(s)...")
        bq.delete_by_ids(bq_client, "documents", "doc_id", extra_doc_ids)
        bq.delete_by_ids(bq_client, "extracted_facts", "doc_id", extra_doc_ids)

    for processor_id in DEMO_TOUCHED_PROCESSOR_IDS:
        snapshot_path = snapshot_dir / f"{processor_id}.json"
        if not snapshot_path.exists():
            print(
                f"{processor_id}: no snapshot found at {snapshot_path} — "
                "run scripts/snapshot_demo_processors.py first. Skipped."
            )
            continue
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
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

        print(
            f"{processor_id}: restored check_results={len(snapshot['check_results'])} "
            f"assessments={len(snapshot['assessments'])} "
            f"agent_runs={len(snapshot['agent_runs'])} memos={len(snapshot['memos'])}"
        )

    print(
        "\nReset complete. The deployed epr-api's cache never expires on its own "
        "(app/store/cache.py's NO_EXPIRY) and this script runs outside that process, "
        "so a currently-running instance will not see this change until either another "
        "live run calls cache.invalidate() + cache.preload() on its own, or the instance "
        "restarts (redeploy, or `gcloud run services update epr-api` to force a new "
        "revision) — restart it before the next demo rehearsal."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore pre-demo state.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    run_reset(args.seed)


if __name__ == "__main__":
    main()
