"""Saves the pre-demo state of every processor a live demo batch can
touch (PWP-01, PWP-03, PWP-05 — api/scripts/generate_demo_extra_docs.py's
DEMO_EXTRA_PLAN plus PWP-05's pure certificate-bump batch) to
data/synthetic/seed-<seed>/pre_demo_snapshot/<processor_id>.json:
check_results, both assessment stages, the latest agent_runs trail, and
memos (en + hi if present).

scripts/reset_demo.py restores from these snapshots rather than
re-running checks/agents/memo live — re-running the agent loop costs
real Gemini money/time every time the developer wants to rehearse the
demo again, and the standing rule is this agent never makes live Gemini
calls anyway. Run this ONCE, before the first live demo click.

Run by the developer — never by the agent (hits real BigQuery).

Usage: uv run python scripts/snapshot_demo_processors.py --seed 42
"""

import argparse
import datetime
import json
from pathlib import Path

from app.store import bq

REPO_ROOT = Path(__file__).resolve().parents[2]

DEMO_TOUCHED_PROCESSOR_IDS = ["PWP-01", "PWP-03", "PWP-05"]
_TABLES = ["check_results", "assessments", "agent_runs", "memos"]


def _jsonable(value):
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    return value


def _serialize_row(row: dict) -> dict:
    return {k: _jsonable(v) for k, v in row.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description="Snapshot pre-demo processor state.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--facts-source", default="extracted", choices=["truth", "extracted"])
    args = parser.parse_args()
    seed, facts_source = args.seed, args.facts_source

    bq_client = bq.get_client()
    out_dir = REPO_ROOT / "data" / "synthetic" / f"seed-{seed}" / "pre_demo_snapshot"
    out_dir.mkdir(parents=True, exist_ok=True)

    for processor_id in DEMO_TOUCHED_PROCESSOR_IDS:
        snapshot = {"seed": seed, "facts_source": facts_source, "processor_id": processor_id}
        for table in _TABLES:
            rows = bq.fetch_rows(
                bq_client, table, "*", seed, processor_id=processor_id, facts_source=facts_source
            )
            snapshot[table] = [_serialize_row(r) for r in rows]

        out_path = out_dir / f"{processor_id}.json"
        out_path.write_text(json.dumps(snapshot, indent=2, sort_keys=True), encoding="utf-8")
        print(
            f"{processor_id}: check_results={len(snapshot['check_results'])} "
            f"assessments={len(snapshot['assessments'])} agent_runs={len(snapshot['agent_runs'])} "
            f"memos={len(snapshot['memos'])} -> {out_path}"
        )

    print(f"\nSnapshot complete for {len(DEMO_TOUCHED_PROCESSOR_IDS)} processor(s).")


if __name__ == "__main__":
    main()
