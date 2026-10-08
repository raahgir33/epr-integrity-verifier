"""Smoke-tests a RUNNING local epr-api against the real dataset.

Run by the developer — never by the agent (hits the API, which itself
talks to real BigQuery/GCS). Start the API first:

    uv run uvicorn app.main:app --reload --port 8080

then, from another terminal:

    uv run python scripts/smoke_api.py

Hits every GET endpoint twice (cold = first request this script makes to
that path, warm = second), prints per-endpoint timings, and checks the
expected shape of the BigQuery-stored no_thinking_run2 acceptance run
(docs/PROGRESS.md's T10 closing entry and the --rescore write that landed
it): F8 caught (deductible) on PWP-05/PWP-08 citing their own SHP-001;
PWP-06/PWP-07/PWP-09 concurring with a deterministic check (C4/F7/F6 —
same evidence those checks already cited, by design, so no separate
soft-signal bump); PWP-01 through PWP-04 and PWP-10 clean (no findings —
run 2's own PWP-10 had no agent finding at all); and GET /health's
consistency_ok true — the one assertion that stands in for "every
processor's full-stage verifiable_t matches what app/store/cache.py's
check_consistency recomputes from the stored agent_runs trail," since the
smoke script itself has no independent way to recompute that figure.

Exit code is 0 only if every check passes; a full report is always
printed first, so a legitimate run-to-run model difference (the agent
loop's findings are themselves a live Gemini call, not deterministic) is
visible in detail rather than hidden behind the first failure.
"""

import argparse
import sys
import time

import requests

DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_BRAND_ID = "BRAND-01"

_F8_DEDUCTIBLE = ["PWP-05", "PWP-08"]
_CONCURS_WITH_CHECK = ["PWP-06", "PWP-07", "PWP-09"]
_CLEAN_NO_FINDINGS = ["PWP-01", "PWP-02", "PWP-03", "PWP-04", "PWP-10"]


class Report:
    def __init__(self) -> None:
        self.timings: list[tuple[str, float, float]] = []  # (label, cold_ms, warm_ms)
        self.checks: list[tuple[str, bool, str]] = []  # (label, passed, detail)

    def add_timing(self, label: str, cold_ms: float, warm_ms: float) -> None:
        self.timings.append((label, cold_ms, warm_ms))

    def check(self, label: str, passed: bool, detail: str) -> None:
        self.checks.append((label, passed, detail))

    def print_and_exit(self) -> None:
        print("\n--- timings (ms) ---")
        print(f"{'endpoint':<45} {'cold':>10} {'warm':>10}")
        for label, cold_ms, warm_ms in self.timings:
            print(f"{label:<45} {cold_ms:>10.1f} {warm_ms:>10.1f}")

        print("\n--- checks ---")
        all_passed = True
        for label, passed, detail in self.checks:
            status = "PASS" if passed else "FAIL"
            if not passed:
                all_passed = False
            print(f"[{status}] {label}: {detail}")

        print(f"\n{'ALL CHECKS PASSED' if all_passed else 'SOME CHECKS FAILED'}")
        sys.exit(0 if all_passed else 1)


def _timed_get(
    session: requests.Session, base_url: str, path: str
) -> tuple[requests.Response, float]:
    start = time.monotonic()
    response = session.get(f"{base_url}{path}")
    elapsed_ms = (time.monotonic() - start) * 1000
    return response, elapsed_ms


def _hit_twice(
    session: requests.Session, base_url: str, path: str, report: Report, label: str | None = None
) -> requests.Response:
    """GETs path twice, records (cold, warm) timings, returns the warm
    response (same content either way for anything in this API — nothing
    here is a live/mutating call)."""
    label = label or path
    _, cold_ms = _timed_get(session, base_url, path)
    second, warm_ms = _timed_get(session, base_url, path)
    report.add_timing(label, cold_ms, warm_ms)
    return second


def _finding_classifications(findings: list[dict]) -> list[str]:
    return [f["classification"] for f in findings]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--brand-id", default=DEFAULT_BRAND_ID)
    args = parser.parse_args()

    session = requests.Session()
    report = Report()

    health = _hit_twice(session, args.base_url, "/health", report).json()
    report.check(
        "consistency_ok",
        health.get("consistency_ok") is True,
        f"GET /health returned consistency_ok={health.get('consistency_ok')!r} — "
        "every processor's full-stage verifiable_t must match what the stored "
        "agent_runs trail recomputes (see app/store/cache.py's check_consistency)",
    )

    processors_body = _hit_twice(session, args.base_url, "/processors", report).json()
    processor_ids = [p["processor_id"] for p in processors_body["processors"]]

    _hit_twice(session, args.base_url, "/evaluation", report)
    _hit_twice(session, args.base_url, "/alerts", report)
    _hit_twice(session, args.base_url, f"/portfolio/{args.brand_id}", report)

    findings_by_processor: dict[str, list[dict]] = {}
    for pid in processor_ids:
        detail = _hit_twice(
            session, args.base_url, f"/processors/{pid}", report, label=f"/processors/{pid}"
        ).json()
        findings_by_processor[pid] = detail.get("findings", [])

        _hit_twice(
            session,
            args.base_url,
            f"/processors/{pid}/documents",
            report,
            label=f"/processors/{pid}/documents",
        )
        reasoning = _hit_twice(
            session,
            args.base_url,
            f"/processors/{pid}/reasoning",
            report,
            label=f"/processors/{pid}/reasoning",
        ).json()

        site_response, site_cold_ms = _timed_get(session, args.base_url, f"/processors/{pid}/site")
        _, site_warm_ms = _timed_get(session, args.base_url, f"/processors/{pid}/site")
        report.add_timing(f"/processors/{pid}/site", site_cold_ms, site_warm_ms)

        docs = session.get(f"{args.base_url}/processors/{pid}/documents").json()["documents"]
        if docs:
            doc_id = docs[0]["doc_id"]
            _hit_twice(
                session,
                args.base_url,
                f"/documents/{doc_id}/file",
                report,
                label=f"/documents/{doc_id}/file",
            )
            _hit_twice(
                session,
                args.base_url,
                f"/documents/{doc_id}/facts",
                report,
                label=f"/documents/{doc_id}/facts",
            )

        if site_response.status_code == 200:
            _hit_twice(
                session, args.base_url, f"/site-images/{pid}", report, label=f"/site-images/{pid}"
            )

        # reasoning's own findings must equal /processors/{id}'s — same
        # reconstruction, both read paths (docs/ARCHITECTURE.md §7).
        report.check(
            f"{pid}: reasoning findings == processor-detail findings",
            reasoning.get("findings") == detail.get("findings"),
            f"{len(reasoning.get('findings', []))} vs {len(detail.get('findings', []))} findings",
        )

    for pid in _F8_DEDUCTIBLE:
        classifications = _finding_classifications(findings_by_processor.get(pid, []))
        matching = [
            f
            for f in findings_by_processor.get(pid, [])
            if f["classification"] == "deductible"
            and f"{pid}-SHP-001" in f.get("cited_shipment_ids", [])
        ]
        cited_ids_seen = [f.get("cited_shipment_ids") for f in findings_by_processor.get(pid, [])]
        report.check(
            f"{pid}: deductible F8-type finding citing its own SHP-001",
            bool(matching),
            f"classifications found: {classifications}, cited_shipment_ids seen: {cited_ids_seen}",
        )

    for pid in _CONCURS_WITH_CHECK:
        classifications = _finding_classifications(findings_by_processor.get(pid, []))
        report.check(
            f"{pid}: has a concurs_with_check finding",
            "concurs_with_check" in classifications,
            f"classifications found: {classifications}",
        )

    for pid in _CLEAN_NO_FINDINGS:
        findings = findings_by_processor.get(pid, [])
        report.check(
            f"{pid}: no findings at all",
            findings == [],
            f"classifications found: {_finding_classifications(findings)}",
        )

    report.print_and_exit()


if __name__ == "__main__":
    main()
