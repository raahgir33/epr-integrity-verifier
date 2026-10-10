"""Restores the pre-demo state for a seed's live event path (docs/
BUILD_PLAN.md T13's accept criterion). Deletes every runs/alerts row,
deletes the demo-batch certificates and the demo-extra documents/
extracted_facts rows, and restores check_results/assessments/agent_runs/
memos for every processor a demo batch can touch from the snapshot
scripts/snapshot_demo_processors.py took before the first live click.

The actual BigQuery mechanics live in app/admin/reset_demo.py's
run_reset() (T13.8) — this script is now just the disk-reading + CLI
glue around it, reading demo_batches.json and pre_demo_snapshot/*.json
from data/synthetic/ on disk. POST /admin/reset-demo (app/main.py) is the
other caller, for the deployed container where data/ doesn't ship.

Zero new Gemini calls, fast, fully deterministic — never re-runs checks/
agents/memo live. Safe to run as many times as the developer wants to
rehearse the demo again.

Run by the developer — never by the agent (hits real BigQuery).

Usage: uv run python scripts/reset_demo.py --seed 42
"""

import argparse
import json
from pathlib import Path

from app.admin import reset_demo as admin_reset_demo
from app.store import bq

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_reset(seed: int) -> None:
    """Disk-reading wrapper around app.admin.reset_demo.run_reset, kept
    here (rather than inlined into main()) so tests/test_reset_demo.py can
    exercise it directly against a fake bq module, the same split
    scripts/run_pipeline.py's run_checks/run_agents/run_memo already
    use."""
    seed_dir = REPO_ROOT / "data" / "synthetic" / f"seed-{seed}"
    snapshot_dir = seed_dir / "pre_demo_snapshot"
    demo_batches = json.loads((seed_dir / "demo_batches.json").read_text(encoding="utf-8"))

    snapshots = {}
    for processor_id in admin_reset_demo.DEMO_TOUCHED_PROCESSOR_IDS:
        snapshot_path = snapshot_dir / f"{processor_id}.json"
        if not snapshot_path.exists():
            print(
                f"{processor_id}: no snapshot found at {snapshot_path} — "
                "run scripts/snapshot_demo_processors.py first. Skipped."
            )
            continue
        snapshots[processor_id] = json.loads(snapshot_path.read_text(encoding="utf-8"))

    bq_client = bq.get_client()
    print("Deleting runs/alerts rows, demo-batch certificates and demo-extra documents...")
    restored = admin_reset_demo.run_reset(bq_client, seed, demo_batches, snapshots)
    for processor_id in restored:
        snapshot = snapshots[processor_id]
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
        "revision) — restart it before the next demo rehearsal. Alternatively, call "
        "POST /admin/reset-demo on the deployed instance directly (T13.8) — it runs this "
        "same reset and re-warms its own cache in the same request."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore pre-demo state.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    run_reset(args.seed)


if __name__ == "__main__":
    main()
