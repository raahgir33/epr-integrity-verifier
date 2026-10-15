"""Cross-endpoint consistency check (docs/PROGRESS.md T13.9).

Confirms certified/verifiable/unverifiable tonnes and risk band agree
everywhere a processor's assessment is shown: GET /stats, GET /processors,
GET /processors/{id}, the clarification-memo/verification-statement
doc_type choice (via app.agents.memo.decide_doc_type, the same pure
decision rule the pipeline uses — reused here rather than re-derived), and
GET /portfolio/{brand_id}'s per-certificate risk band and apportioned
total. Portfolio's total_verifiable_t is a derived apportionment across
certificates (docs/ARCHITECTURE.md §7), not a traced per-processor figure,
so it is recomputed from the certificate rows' own ratio arithmetic and
compared to the endpoint's own total — not compared directly to any
processor-level total.

GET requests only — this script never calls a POST/PUT/DELETE endpoint,
so it cannot start a demo run, trigger a reset, or otherwise mutate
anything on the service it points at. It still talks to a live API
(local or deployed), which itself reads from BigQuery, the same category
of thing scripts/smoke_api.py's docstring warns is normally "run by the
developer, never by the agent" — run it with that in mind.

Prints each mismatch found (nothing on success beyond a summary line) and
exits 1 if any were found, 0 otherwise.

Usage: uv run python scripts/check_consistency.py <base_url>
       uv run python scripts/check_consistency.py http://localhost:8080
       uv run python scripts/check_consistency.py https://epr-api-xxxx.a.run.app
"""

import argparse
import sys

import requests

from app.agents.memo import decide_doc_type

TOL = 1e-6
PORTFOLIO_TOL = 0.02  # /portfolio's own totals are round(..., 2) server-side
MONTHLY_FLOW_TOL = 0.02  # get_monthly_flow rounds each month to 2dp before summing

_STAGE_FIELDS = (
    "certified_t",
    "verified_inbound_t",
    "capacity_limit_t",
    "verifiable_t",
    "unverifiable_t",
    "risk_band",
)


def _get(session: requests.Session, base_url: str, path: str, **params: str) -> dict:
    response = session.get(f"{base_url.rstrip('/')}{path}", params=params, timeout=30)
    response.raise_for_status()
    return response.json()


def _close(a: float | None, b: float | None, tol: float = TOL) -> bool:
    if a is None or b is None:
        return a == b
    return abs(a - b) <= tol


def _compare_stage(label: str, a: dict | None, b: dict | None, mismatches: list[str]) -> None:
    if (a is None) != (b is None):
        mismatches.append(f"{label}: one side missing ({a!r} vs {b!r})")
        return
    if a is None:
        return
    for field in _STAGE_FIELDS:
        av, bv = a.get(field), b.get(field)
        same = (av == bv) if field == "risk_band" else _close(av, bv)
        if not same:
            mismatches.append(f"{label}.{field}: {av!r} != {bv!r}")


def check_stats(
    session: requests.Session, base_url: str, processors: dict[str, dict], mismatches: list[str]
) -> None:
    stats = _get(session, base_url, "/stats")
    expected_certified = sum(p["checks_only"]["certified_t"] for p in processors.values())
    expected_unverifiable = sum(
        (p["full"] or p["checks_only"])["unverifiable_t"] for p in processors.values()
    )
    if not _close(stats["certified_t_total"], expected_certified):
        mismatches.append(
            f"/stats.certified_t_total: {stats['certified_t_total']} "
            f"!= Σ checks_only.certified_t {expected_certified}"
        )
    if not _close(stats["unverifiable_t_total"], expected_unverifiable):
        mismatches.append(
            f"/stats.unverifiable_t_total: {stats['unverifiable_t_total']} "
            f"!= Σ (full ?? checks_only).unverifiable_t {expected_unverifiable}"
        )
    if stats["processors_count"] != len(processors):
        mismatches.append(
            f"/stats.processors_count: {stats['processors_count']} "
            f"!= len(/processors)={len(processors)}"
        )


def check_processor_detail_and_memo(
    session: requests.Session, base_url: str, pid: str, summary: dict, mismatches: list[str]
) -> None:
    detail = _get(session, base_url, f"/processors/{pid}")
    _compare_stage(
        f"{pid} checks_only (/processors vs /processors/{{id}})",
        summary["checks_only"],
        detail["checks_only"],
        mismatches,
    )
    _compare_stage(
        f"{pid} full (/processors vs /processors/{{id}})",
        summary["full"],
        detail["full"],
        mismatches,
    )
    if summary["agent_status"] != detail["agent_status"]:
        mismatches.append(
            f"{pid}.agent_status: {summary['agent_status']!r} != {detail['agent_status']!r}"
        )

    effective = detail["full"] or detail["checks_only"]
    try:
        memo = _get(session, base_url, f"/processors/{pid}/memo", lang="en")
    except requests.HTTPError as exc:
        mismatches.append(f"{pid}: GET /processors/{pid}/memo?lang=en failed ({exc})")
        return

    expected_doc_type = decide_doc_type(effective, detail["check_results"], detail["findings"])
    if memo["doc_type"] != expected_doc_type:
        mismatches.append(
            f"{pid}.memo.doc_type: {memo['doc_type']!r} != expected {expected_doc_type!r} "
            f"(risk_band={effective['risk_band']!r})"
        )

    check_monthly_flow(pid, detail, mismatches)


def check_monthly_flow(pid: str, detail: dict, mismatches: list[str]) -> None:
    """The monthly flow chart against the figures printed above it (T17).

    Both sums are compared to **checks_only**, deliberately. The chart is
    a checks-level view: app/store/cache.py's get_monthly_flow applies no
    agent exclusions, so a processor with a confirmed finding has a lower
    full.verified_inbound_t than its own chart sums to, correctly.

    certified_t is also compared unfiltered, which is the point: the
    chart lists every month a certificate exists in, while
    checks_only.certified_t is financial-year-to-date
    (app/checks/capacity.py's certified_t_fy_to_date). A certificate
    outside the current FY therefore shows on the chart but not in the
    header — exactly the divergence a demo batch dated in the next FY
    produces, and exactly what a viewer would see and disbelieve."""
    flow = detail["monthly_flow"]
    checks_only = detail["checks_only"]
    flow_certified = round(sum(row["certified_t"] for row in flow), 2)
    flow_verified = round(sum(row["verified_inbound_t"] for row in flow), 2)

    if not _close(flow_certified, checks_only["certified_t"], tol=MONTHLY_FLOW_TOL):
        mismatches.append(
            f"{pid}.monthly_flow: Σ certified_t {flow_certified} != "
            f"checks_only.certified_t {checks_only['certified_t']} — the chart and the "
            f"header disagree (a certificate outside the current financial year?)"
        )
    if not _close(flow_verified, checks_only["verified_inbound_t"], tol=MONTHLY_FLOW_TOL):
        mismatches.append(
            f"{pid}.monthly_flow: Σ verified_inbound_t {flow_verified} != "
            f"checks_only.verified_inbound_t {checks_only['verified_inbound_t']} — the chart "
            f"and the header disagree (a verified shipment with no month?)"
        )


def check_portfolio(
    session: requests.Session, base_url: str, processors: dict[str, dict], mismatches: list[str]
) -> None:
    brands = _get(session, base_url, "/brands")["brands"]
    for brand in brands:
        bid = brand["brand_id"]
        portfolio = _get(session, base_url, f"/portfolio/{bid}")
        recomputed_total = 0.0
        for cert in portfolio["certificates"]:
            pid = cert["processor_id"]
            proc = processors.get(pid)
            if proc is None:
                mismatches.append(
                    f"/portfolio/{bid} certificate {cert['certificate_id']}: "
                    f"references unknown processor {pid!r}"
                )
                continue
            stage = proc["full"] or proc["checks_only"]
            if cert["processor_risk_band"] != stage["risk_band"]:
                mismatches.append(
                    f"/portfolio/{bid} certificate {cert['certificate_id']}: "
                    f"processor_risk_band {cert['processor_risk_band']!r} != "
                    f"{pid}'s own risk_band {stage['risk_band']!r}"
                )
            ratio = stage["verifiable_t"] / stage["certified_t"] if stage["certified_t"] else 0.0
            recomputed_total += cert["quantity_t"] * ratio
        recomputed_total = round(recomputed_total, 2)
        if not _close(portfolio["total_verifiable_t"], recomputed_total, tol=PORTFOLIO_TOL):
            mismatches.append(
                f"/portfolio/{bid}.total_verifiable_t: {portfolio['total_verifiable_t']} "
                f"!= recomputed from certificates {recomputed_total}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url")
    args = parser.parse_args()

    session = requests.Session()
    mismatches: list[str] = []

    processors_resp = _get(session, args.base_url, "/processors")
    processors = {p["processor_id"]: p for p in processors_resp["processors"]}

    check_stats(session, args.base_url, processors, mismatches)
    for pid, summary in processors.items():
        check_processor_detail_and_memo(session, args.base_url, pid, summary, mismatches)
    check_portfolio(session, args.base_url, processors, mismatches)

    if mismatches:
        for mismatch in mismatches:
            print(mismatch)
        sys.exit(1)

    print(
        f"OK — {len(processors)} processors checked across /stats, /processors, "
        f"/processors/{{id}}, memo doc_type, monthly flow, and portfolio — no mismatches."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
