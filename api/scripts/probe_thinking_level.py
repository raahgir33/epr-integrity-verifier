"""One-off probe: does types.ThinkingConfig(thinking_level="low") work for
extraction on this model/region, and does it actually reduce thinking vs
model-default thinking (no thinking config sent, confirmed to give
thoughts_token_count=0 — see docs/PROGRESS.md)?

Never send thinking_budget, or thinking_level="minimal", to Gemini 3.x
models (developer instruction, 2026-10-07; enforced in app/llm.py, not
just documented) — this script only ever tries "low".

10 documents, covering all 7 document types, including a Hindi document
and a weighbridge photo (also Hindi) — same PWP-01 set the original
46-document trial extracted at 100% accuracy, so results are directly
comparable.

Run by the developer — never by the agent (hits real Vertex AI).

Usage: uv run python scripts/probe_thinking_level.py
"""

import json
from pathlib import Path

from app.config import settings
from app.eval.evaluate import extraction_field_accuracy
from app.ingest.extract import MIME_TYPE_BY_DOC_TYPE, PROMPT_BY_DOC_TYPE, facts_to_field_rows
from app.ingest.schemas import SCHEMA_BY_DOC_TYPE
from app.llm import GeminiClient
from app.store import gcs
from scripts.load_dossiers import document_gcs_path

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED = 42
THINKING_LEVEL = "low"

PROBE_DOC_IDS = [
    "PWP-01-CTO-001",
    "PWP-01-EPR_REGISTRATION-002",
    "PWP-01-INBOUND_INVOICE-003",  # Hindi
    "PWP-01-EWAY_BILL-004",  # Hindi
    "PWP-01-WEIGHBRIDGE_SLIP-005",  # Hindi, weighbridge photo
    "PWP-01-INBOUND_INVOICE-006",
    "PWP-01-EWAY_BILL-007",
    "PWP-01-WEIGHBRIDGE_SLIP-008",
    "PWP-01-OUTBOUND_INVOICE-030",
    "PWP-01-ELECTRICITY_BILL-035",
]


def main() -> None:
    gt_path = REPO_ROOT / "data" / "synthetic" / f"seed-{SEED}" / "ground_truth.json"
    ground_truth = json.loads(gt_path.read_text(encoding="utf-8"))
    docs_by_id = {d["doc_id"]: d for d in ground_truth["documents"]}

    llm_client = GeminiClient()
    gcs_client = gcs.get_client()

    results = []
    for doc_id in PROBE_DOC_IDS:
        doc = docs_by_id[doc_id]
        doc_type = doc["doc_type"]
        gcs_path = document_gcs_path(SEED, doc)
        data = gcs.download_bytes(gcs_client, settings.dossier_bucket, gcs_path)
        try:
            facts = llm_client.extract(
                data,
                MIME_TYPE_BY_DOC_TYPE[doc_type],
                PROMPT_BY_DOC_TYPE[doc_type],
                SCHEMA_BY_DOC_TYPE[doc_type],
                purpose=f"probe_thinking_level:{doc_type}",
                thinking_level=THINKING_LEVEL,
            )
            results.append({"doc_id": doc_id, "doc_type": doc_type, "status": "ok", "facts": facts})
            print(f"  OK     {doc_id} ({doc_type}, lang={doc['lang']})")
        except Exception as exc:  # noqa: BLE001 — a probe records every failure, never raises
            results.append(
                {"doc_id": doc_id, "doc_type": doc_type, "status": "failed", "error": str(exc)}
            )
            print(f"  FAILED {doc_id} ({doc_type}, lang={doc['lang']}): {exc}")

    ok = [r for r in results if r["status"] == "ok"]
    print(f"\n{len(ok)}/{len(results)} ok")

    if ok:
        extracted_rows = []
        for r in ok:
            for field_row in facts_to_field_rows(r["facts"]):
                extracted_rows.append({"doc_id": r["doc_id"], **field_row})
        probe_gt_docs = [docs_by_id[r["doc_id"]] for r in ok]
        report = extraction_field_accuracy(extracted_rows, probe_gt_docs)
        overall = report["overall"]
        acc = overall["accuracy"] or 0.0
        print(f"Accuracy on successful docs: {overall['correct']}/{overall['total']} ({acc:.1%})")

    call_log = llm_client.flush_call_log()
    print("\nPer-call thinking_tokens (thoughts_token_count):")
    for record in call_log:
        status = "ok" if record["success"] else "failed"
        print(f"  {record['purpose']:40s} {status:6s} thinking_tokens={record['thinking_tokens']}")


if __name__ == "__main__":
    main()
