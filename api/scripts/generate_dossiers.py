"""Generates the full synthetic EPR dossier world for a given seed:
10 processors' documents (PDFs and weighbridge PNGs), certificates.csv,
processors/suppliers/brands/demo_batches JSON, and ground_truth.json.

See docs/DATA_SPEC.md §2-§6. Runs only on the developer's machine, never
on Cloud Run — Playwright/Chromium aren't in the deployed image.

Usage: uv run python scripts/generate_dossiers.py --seed 42
       uv run python scripts/generate_dossiers.py --seed 42 --no-render
"""

import argparse
import json
import shutil
from pathlib import Path

from scripts.dossier_gen.ground_truth import build_ground_truth
from scripts.dossier_gen.manifests import (
    brands_to_json,
    build_certificates_csv,
    build_demo_batches,
    processors_to_json,
    suppliers_to_json,
)
from scripts.dossier_gen.render import Renderer
from scripts.dossier_gen.rng import new_rng
from scripts.dossier_gen.shipments import Dossier, assign_cross_processor_identifiers, build_dossier
from scripts.dossier_gen.world import Processor, build_brands, build_processors, build_suppliers

REPO_ROOT = Path(__file__).resolve().parents[2]

# Everything this script itself writes under data/synthetic/seed-<seed>/ —
# used to clean a stale run before regenerating. Deliberately NOT a
# directory-wide wipe: data/synthetic/seed-<seed>/ also holds artifacts
# from later, non-generator pipeline stages (site_assessments.json from
# --stage site's real Earth Engine calls; agent_probe_runs/ from
# scripts/probe_agent_thinking.py's real Gemini calls) that this script
# must never delete as collateral damage — both are expensive/live-call
# outputs, unlike anything here, which is cheap to regenerate from the
# seed alone.
_GENERATOR_OWNED_RELATIVE_PATHS = (
    "ground_truth.json",
    "processors.json",
    "suppliers.json",
    "brands.json",
    "demo_batches.json",
    "certificates.csv",
    "documents",
)


def _clean_generator_outputs(out_dir: Path) -> None:
    for relative_path in _GENERATOR_OWNED_RELATIVE_PATHS:
        path = out_dir / relative_path
        if path.is_dir():
            shutil.rmtree(path)
        elif path.exists():
            path.unlink()


def build_all_dossiers(processors: list[Processor], suppliers, rng) -> dict[str, Dossier]:
    """PWP-01 is built first (and forced to carry the Hindi sample) since
    PWP-10's F4 duplicate copies one of its records."""
    by_id = {p.processor_id: p for p in processors}
    dossiers: dict[str, Dossier] = {
        "PWP-01": build_dossier(by_id["PWP-01"], suppliers, rng, force_hindi=True)
    }
    for p in processors:
        if p.processor_id == "PWP-01":
            continue
        f4_source = dossiers["PWP-01"] if "F4" in p.issue_types else None
        dossiers[p.processor_id] = build_dossier(p, suppliers, rng, f4_source=f4_source)
    return dossiers


def run_data_pipeline(seed: int) -> dict:
    """Everything except rendering: deterministic, pure-Python, fast. The
    single source of truth for both the CLI (--no-render) and the test
    suite's determinism checks, so they can't drift apart."""
    rng = new_rng(seed)
    processors = build_processors(rng)
    suppliers = build_suppliers(rng)
    brands = build_brands()
    dossiers = build_all_dossiers(processors, suppliers, rng)
    # Cross-processor/supplier identifier series (invoice_no, ewb_no) can
    # only be finalized once every dossier — and every supplier's full
    # usage across all of them — exists (T10 realism fix,
    # docs/PROGRESS.md). Must run before build_ground_truth, which
    # serializes the final document fields.
    assign_cross_processor_identifiers(dossiers, suppliers, rng)
    ground_truth = build_ground_truth(seed, processors, dossiers)
    return {
        "seed": seed,
        "processors": processors,
        "suppliers": suppliers,
        "brands": brands,
        "dossiers": dossiers,
        "ground_truth": ground_truth,
    }


def render_all_documents(dossiers: dict[str, Dossier], out_dir: Path, rng) -> None:
    with Renderer() as renderer:
        for processor_id, dossier in dossiers.items():
            proc_dir = out_dir / "documents" / processor_id
            for doc in dossier.documents:
                if doc["doc_type"] == "weighbridge_slip":
                    path = proc_dir / f"{doc['doc_id']}.png"
                    renderer.render_weighbridge_png(doc["fields"], doc["lang"], path, rng)
                else:
                    path = proc_dir / f"{doc['doc_id']}.pdf"
                    renderer.render_pdf(doc["doc_type"], doc["fields"], doc["lang"], path)


def write_json(path: Path, data) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8"
    )


def write_manifests(out_dir: Path, pipeline: dict) -> None:
    processors = pipeline["processors"]
    suppliers = pipeline["suppliers"]
    brands = pipeline["brands"]
    dossiers = pipeline["dossiers"]
    ground_truth = pipeline["ground_truth"]
    gt_by_id = {pe["processor_id"]: pe for pe in ground_truth["processors"]}

    write_json(out_dir / "ground_truth.json", ground_truth)
    write_json(out_dir / "processors.json", processors_to_json(processors))
    write_json(out_dir / "suppliers.json", suppliers_to_json(suppliers))
    write_json(out_dir / "brands.json", brands_to_json(brands))
    write_json(out_dir / "demo_batches.json", build_demo_batches(processors, gt_by_id))
    (out_dir / "certificates.csv").write_text(
        build_certificates_csv(processors, dossiers, brands), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the synthetic EPR dossier world.")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="Skip Playwright rendering; write only JSON/CSV manifests. Fast — for quick "
        "iteration on the data pipeline, not a substitute for the full run before a demo.",
    )
    args = parser.parse_args()

    out_dir = REPO_ROOT / "data" / "synthetic" / f"seed-{args.seed}"
    _clean_generator_outputs(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pipeline = run_data_pipeline(args.seed)
    write_manifests(out_dir, pipeline)

    total_docs = sum(len(d.documents) for d in pipeline["dossiers"].values())
    if args.no_render:
        print(f"Generated seed {args.seed}: {len(pipeline['processors'])} processors, ", end="")
        print(f"{total_docs} documents described (--no-render: not rendered)")
    else:
        # A separately-seeded stream for render-time randomness (Pillow
        # degradation), so it doesn't entangle with document-content generation.
        render_rng = new_rng(args.seed)
        render_all_documents(pipeline["dossiers"], out_dir, render_rng)
        print(f"Generated seed {args.seed}: {len(pipeline['processors'])} processors, ", end="")
        print(f"{total_docs} documents")
    print(f"-> {out_dir}")


if __name__ == "__main__":
    main()
