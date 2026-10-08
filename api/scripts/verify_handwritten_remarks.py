"""One-off verification for the F9/H5 handwritten-remark overlay (docs/
DATA_SPEC.md §5): confirms Gemini actually reads the handwritten Hindi
text off the weighbridge slip PHOTO, not just the typed fields — the
whole point of F9/H5 as agent-only seeded patterns.

Finds the F9 weighbridge slip (PWP-02) and the H5 weighbridge slip
(PWP-04) from ground_truth.json, reads back their extracted `remarks`
field from `extracted_facts`, and asserts an exact string match against
ground truth. Prints both values regardless of outcome, so a mismatch is
visible, not just a pass/fail flag.

Run by the developer — never by the agent (reads real BigQuery). Requires
--stage extract to have already run for PWP-02 and PWP-04 this seed.

Usage: uv run python scripts/verify_handwritten_remarks.py
"""

import json
from pathlib import Path

from google.cloud import bigquery

from app.config import settings
from app.store import bq

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = 42

_EXPECTED = {
    "F9": {"processor_id": "PWP-02", "remark": "माल वापस भेजा"},
    "H5": {"processor_id": "PWP-04", "remark": "तिरपाल फटा"},
}


def _load_ground_truth(seed: int) -> dict:
    path = REPO_ROOT / "data" / "synthetic" / f"seed-{seed}" / "ground_truth.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _find_weighbridge_doc_id(ground_truth: dict, processor_id: str, remark: str) -> str:
    matches = [
        doc["doc_id"]
        for doc in ground_truth["documents"]
        if doc["processor_id"] == processor_id
        and doc["doc_type"] == "weighbridge_slip"
        and doc["fields"].get("remarks", {}).get("canonical") == remark
    ]
    assert len(matches) == 1, (
        f"expected exactly one {processor_id} weighbridge slip with remarks={remark!r}, "
        f"found {len(matches)}: {matches}"
    )
    return matches[0]


def _fetch_extracted_remarks(client, seed: int, doc_ids: list[str]) -> dict[str, str | None]:
    query = f"""
        SELECT doc_id, printed_value
        FROM `{settings.gcp_project}.{settings.bq_dataset}.extracted_facts`
        WHERE seed = @seed AND doc_id IN UNNEST(@doc_ids) AND field_name = 'remarks'
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[
            bigquery.ScalarQueryParameter("seed", "INTEGER", seed),
            bigquery.ArrayQueryParameter("doc_ids", "STRING", doc_ids),
        ]
    )
    job = client.query(query, job_config=job_config, location=settings.vertex_location)
    rows = {row["doc_id"]: row["printed_value"] for row in job.result()}
    return {doc_id: rows.get(doc_id) for doc_id in doc_ids}


def main() -> None:
    ground_truth = _load_ground_truth(SEED)
    doc_ids_by_label = {
        label: _find_weighbridge_doc_id(ground_truth, info["processor_id"], info["remark"])
        for label, info in _EXPECTED.items()
    }

    client = bq.get_client()
    extracted = _fetch_extracted_remarks(client, SEED, list(doc_ids_by_label.values()))

    all_match = True
    for label, info in _EXPECTED.items():
        doc_id = doc_ids_by_label[label]
        expected = info["remark"]
        actual = extracted.get(doc_id)
        status = "PASS" if actual == expected else "FAIL"
        all_match &= actual == expected
        print(f"{label} ({info['processor_id']}, {doc_id}): {status}")
        print(f"  ground truth : {expected!r}")
        print(f"  Gemini read  : {actual!r}")

    print("\nALL MATCH" if all_match else "\nMISMATCH — see above")


if __name__ == "__main__":
    main()
