"""Smoke-tests a RUNNING local epr-api against the real dataset.

Run by the developer — never by the agent (hits the API, which itself
talks to real BigQuery/GCS). Start the API first:

    uv run uvicorn app.main:app --reload --port 8080

then, from another terminal:

    uv run python scripts/smoke_api.py

Hits every GET endpoint twice (cold = first request this script makes to
that path, warm = second), prints per-endpoint timings, and checks the
shape of the stored EXTRACTED-facts agent run — what the deployed service
actually serves (DEFAULT_FACTS_SOURCE=extracted).

The expectations here were previously pinned to T10's truth-facts
`no_thinking_run2` acceptance run, and every one of them failed once the
live service moved to extracted facts: shipment ids gained an "-EXT-"
segment and renumbered, and the agent-only findings landed on different
processors. They are pinned to extracted mode now, and the script asserts
`meta.facts_source` up front so a service pointed back at truth reports
that directly instead of as six unexplained finding mismatches.

What is checked, and why each is stable enough to assert:

  * Agent-only (no deterministic check behind them) findings are
    deductible on PWP-02, PWP-05 and PWP-08 — the three seed-42
    processors carrying a semantic or handwritten contradiction. PWP-02's
    is the handwritten Hindi weighbridge remark, which only extracted
    mode exercises at all: truth mode loads that remark canonically, so
    the agent never had to read the photo and this processor looked
    clean. Asserted by classification plus "cites one of its OWN
    shipments", never by a hardcoded shipment index — positions are
    seeded-random per processor and the "-EXT-" ids renumber.
  * PWP-01, PWP-03 and PWP-04 are the genuinely clean processors
    (docs/DATA_SPEC.md §5) and must raise no deductible finding. A
    non-deducting review flag is tolerated: the guardrails are designed
    to keep a weak observation visible rather than silent, and the
    held-out evaluation measures that false-flag rate properly.
  * Every cited shipment id belongs to the processor citing it, on every
    processor — the cited-id guardrail (app/agents/orchestrator.py's
    _filter_objection), and the one finding-level invariant that holds
    regardless of what the model said on any given run.

Deliberately NOT asserted: the exact finding count or classification mix
per processor. Those are a live Gemini call's output; the held-out
evaluation measures run-to-run finding-set agreement at 47% pooled
Jaccard, so pinning them would make this script flaky rather than
informative. Risk bands and tonnes, which ARE stable (9/10 and 10/10
across three runs), are covered by scripts/check_consistency.py.

GET /health no longer carries consistency_ok — T13.8 reduced it to
exactly {"status": "ok"}, with _consistency_status still computed and
logged at startup. Run scripts/check_consistency.py <base-url> for that;
this script only checks /health's own contract.

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

# Seeded agent-only contradictions (docs/DATA_SPEC.md §5): a semantic one
# on PWP-05/PWP-08, a handwritten Hindi weighbridge remark on PWP-02.
# No deterministic check sees any of them.
_AGENT_ONLY_DEDUCTIBLE = ["PWP-02", "PWP-05", "PWP-08"]
# The three processors with nothing seeded at all.
_CLEAN_NO_DEDUCTIONS = ["PWP-01", "PWP-03", "PWP-04"]
_EXPECTED_FACTS_SOURCE = "extracted"


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


def _own_shipment(processor_id: str, shipment_id: str) -> bool:
    """Extracted mode numbers a processor's shipments
    f"{processor_id}-EXT-SHP-{i:03d}" (app/ingest/normalize.py's
    match_shipments_from_extracted); truth mode omits the "EXT-" segment,
    and the index differs between the two because positions are
    seeded-random per processor. Both forms start with the processor's
    own id, which is the part worth asserting: a finding must never cite
    another processor's shipment."""
    return shipment_id.startswith(f"{processor_id}-")


def _cited_ids(findings: list[dict]) -> list[str]:
    return [sid for f in findings for sid in f.get("cited_shipment_ids", [])]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--brand-id", default=DEFAULT_BRAND_ID)
    args = parser.parse_args()

    session = requests.Session()
    report = Report()

    health = _hit_twice(session, args.base_url, "/health", report).json()
    report.check(
        "health contract",
        health == {"status": "ok"},
        f"GET /health returned {health!r}, expected exactly {{'status': 'ok'}} (T13.8). "
        "Consistency is scripts/check_consistency.py's job, not this script's.",
    )

    processors_body = _hit_twice(session, args.base_url, "/processors", report).json()
    processor_ids = [p["processor_id"] for p in processors_body["processors"]]

    facts_source = (processors_body.get("meta") or {}).get("facts_source")
    report.check(
        "facts_source",
        facts_source == _EXPECTED_FACTS_SOURCE,
        f"serving {facts_source!r}; every finding expectation below is pinned to "
        f"{_EXPECTED_FACTS_SOURCE!r}, so they will all fail against another source",
    )

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

    for pid in _AGENT_ONLY_DEDUCTIBLE:
        findings = findings_by_processor.get(pid, [])
        matching = [
            f
            for f in findings
            if f["classification"] == "deductible"
            and any(_own_shipment(pid, sid) for sid in f.get("cited_shipment_ids", []))
        ]
        report.check(
            f"{pid}: deductible agent-only finding citing one of its own shipments",
            bool(matching),
            f"classifications found: {_finding_classifications(findings)}, "
            f"cited_shipment_ids seen: {[f.get('cited_shipment_ids') for f in findings]}",
        )

    for pid in _CLEAN_NO_DEDUCTIONS:
        findings = findings_by_processor.get(pid, [])
        deductible = [f for f in findings if f["classification"] == "deductible"]
        report.check(
            f"{pid}: clean processor, no deductible finding",
            not deductible,
            f"classifications found: {_finding_classifications(findings)}"
            + (" (a non-deducting review flag here is tolerated)" if findings else ""),
        )

    # Holds on every processor regardless of what the model said: the
    # cited-id guardrail filters every citation against that processor's
    # own verified shipments before a finding is ever classified.
    for pid in processor_ids:
        foreign = [
            sid
            for sid in _cited_ids(findings_by_processor.get(pid, []))
            if not _own_shipment(pid, sid)
        ]
        report.check(
            f"{pid}: every cited shipment is its own",
            not foreign,
            f"foreign ids cited: {foreign}" if foreign else "no cross-processor citations",
        )

    report.print_and_exit()


if __name__ == "__main__":
    main()
