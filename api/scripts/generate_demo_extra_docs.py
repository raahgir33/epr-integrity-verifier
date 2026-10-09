"""Generates the two "live demo" extra shipments T13 needs (docs/
PROGRESS.md's T13 plan) — content that exists nowhere in the main
committed dossier:

  PWP-01 (clean): one ordinary new shipment, nothing planted — the "clean
  batch that passes" demo, so the live event path isn't rigged to always
  alarm.
  PWP-03 (clean): one new shipment whose weighbridge slip carries a
  planted handwritten Hindi remark ("माल नहीं उतारा" — goods not
  unloaded), the same F9-style mechanism as the real seeded F9 (PWP-02)
  but a DIFFERENT phrase, to avoid any confusion between the two — the
  "new agent-only issue" demo, showing the agent catching something no
  deterministic check can.

Deliberately NOT part of generate_dossiers.py's own output: run this
AFTER generate_dossiers.py, never before — it reads the already-committed
ground_truth.json/processors.json/suppliers.json/demo_batches.json for
this seed and only adds to data/synthetic/seed-<seed>/demo_extra/, never
touching documents/ or ground_truth.json. Deterministic and idempotent:
re-running overwrites the same demo_extra/ output and the same two
demo_batches.json entries, byte-for-byte, same as every other generator
script in this project.

Run by the developer — never by the agent (renders via headless
Chromium/Playwright, same as generate_dossiers.py).

Usage: uv run python scripts/generate_demo_extra_docs.py --seed 42
"""

import argparse
import json
import random
from pathlib import Path

from scripts.dossier_gen.demo_extra import plan_demo_extra_shipment
from scripts.dossier_gen.render import Renderer
from scripts.dossier_gen.shipments import FY_MONTHS
from scripts.load_dossiers import document_local_filename, document_mime_type

REPO_ROOT = Path(__file__).resolve().parents[2]

# (processor_id, remark_hi) — remark_hi=None means an ordinary, nothing-
# planted shipment. Picked deliberately away from any processor that
# already carries real handwriting (PWP-02's real F9, PWP-04's real H5),
# so the live demo's planted remark is never shown alongside an unrelated
# one on the same processor.
DEMO_EXTRA_PLAN: list[tuple[str, str | None]] = [
    ("PWP-01", None),
    ("PWP-03", "माल नहीं उतारा"),
]


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate T13's live-demo extra shipments.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    seed = args.seed

    seed_dir = REPO_ROOT / "data" / "synthetic" / f"seed-{seed}"
    ground_truth = _load_json(seed_dir / "ground_truth.json")
    processors_by_id = {p["processor_id"]: p for p in _load_json(seed_dir / "processors.json")}
    suppliers = _load_json(seed_dir / "suppliers.json")
    demo_batches = _load_json(seed_dir / "demo_batches.json")
    demo_batches_by_id = {b["processor_id"]: b for b in demo_batches}
    ground_truth_docs = ground_truth["documents"]
    as_of_month = FY_MONTHS[-1]

    with Renderer() as renderer:
        for processor_id, remark_hi in DEMO_EXTRA_PLAN:
            processor = processors_by_id[processor_id]
            rng = random.Random(f"{seed}-{processor_id}-demo")
            documents, shipment = plan_demo_extra_shipment(
                processor, suppliers, ground_truth_docs, rng, as_of_month, remark_hi
            )

            out_dir = seed_dir / "demo_extra" / processor_id
            manifest_docs = []
            for doc in documents:
                filename = document_local_filename(doc)
                output_path = out_dir / filename
                if doc["doc_type"] == "weighbridge_slip":
                    renderer.render_weighbridge_png(doc["fields"], doc["lang"], output_path, rng)
                else:
                    renderer.render_pdf(doc["doc_type"], doc["fields"], doc["lang"], output_path)
                manifest_docs.append(
                    {
                        "doc_id": doc["doc_id"],
                        "doc_type": doc["doc_type"],
                        "processor_id": processor_id,
                        "lang": doc["lang"],
                        "gcs_path": f"seed-{seed}/demo_extra/{processor_id}/{filename}",
                        "mime_type": document_mime_type(doc),
                    }
                )

            _write_json(
                out_dir / "manifest.json",
                {"documents": manifest_docs, "shipment": shipment, "remark_hi": remark_hi},
            )

            batch = demo_batches_by_id[processor_id]
            batch["extra_document_ids"] = [d["doc_id"] for d in manifest_docs]
            batch["quantity_t"] = shipment["invoice_qty_t"]
            batch["period_month"] = as_of_month

            print(
                f"{processor_id}: shipment {shipment['shipment_id']} "
                f"qty={shipment['invoice_qty_t']}t net={shipment['weighbridge_net_t']}t "
                f"remark={'yes' if remark_hi else 'no'} -> {out_dir}"
            )

    _write_json(seed_dir / "demo_batches.json", demo_batches)
    print(f"\nPatched demo_batches.json for {len(DEMO_EXTRA_PLAN)} processor(s).")


if __name__ == "__main__":
    main()
