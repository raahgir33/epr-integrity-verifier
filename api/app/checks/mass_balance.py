"""C2a (input balance) and C2b (output plausibility). docs/DATA_SPEC.md §4,
§4a. Applicability (C2b is recycler-only) is runner.py's job, not this
module's — these functions assume they are only called where they apply.
"""

from app.checks import params
from app.checks.consistency import shipment_passes_c4
from app.checks.duplicates import shipment_passes_c5
from app.checks.transport import shipment_passes_c3a, shipment_passes_c3b
from app.models.checks import CheckResult


def verified_inbound_shipment_ids(
    shipments: list[dict],
    duplicate_keys: dict[str, dict],
    excluded_shipment_ids: frozenset[str] = frozenset(),
) -> frozenset[str]:
    """The shipment_ids verified_inbound_tonnes (below) would sum — docs/
    DATA_SPEC.md §4a.1's "matched, passes C3/C4/C5" predicate, exposed as
    an id set rather than a total so callers (app/agents/orchestrator.py's
    systemic-finding guard) can reason about *which* shipments a finding
    cites relative to the full verified set, not just how many tonnes.

    A shipment missing a field a check needs (shipment_passes_c3a etc.
    returning None) is treated as not failing that check, not as failing
    it: a matched shipment always carries the fields its own matching
    required (vehicle number, time window, quantities), so None here would
    mean a genuine data gap unrelated to the check itself, not grounds to
    exclude a shipment that was otherwise physically evidenced.
    """
    ids = set()
    for s in shipments:
        if s["shipment_id"] in excluded_shipment_ids:
            continue
        if s.get("match_status") != "matched":
            continue
        if shipment_passes_c3a(s) is False:
            continue
        if shipment_passes_c3b(s) is False:
            continue
        if shipment_passes_c4(s) is False:
            continue
        if not shipment_passes_c5(s["shipment_id"], duplicate_keys):
            continue
        if s.get("weighbridge_net_t") is not None:
            ids.add(s["shipment_id"])
    return frozenset(ids)


def verified_inbound_tonnes(
    shipments: list[dict],
    duplicate_keys: dict[str, dict],
    excluded_shipment_ids: frozenset[str] = frozenset(),
) -> float:
    """docs/DATA_SPEC.md §4a.1: sum of weighbridge net tonnes of matched
    shipments that pass C3, C4 and C5, minus any shipment cited by a
    confirmed agent finding (T10, e.g. F8-style semantic contradictions —
    see app/agents/orchestrator.py).

    excluded_shipment_ids defaults to empty, so the checks-only call sites
    (check_c2a below, and agents/scorer.py's "checks_only" stage) are
    byte-for-byte unchanged from before T10 — this is the same function
    serving both the "checks_only" and "full" assessment stages, not a
    fork of it.

    Shared by check_c2a (below) and agents/scorer.py, so the definition of
    "verified" lives in exactly one place.
    """
    verified_ids = verified_inbound_shipment_ids(shipments, duplicate_keys, excluded_shipment_ids)
    by_id = {s["shipment_id"]: s for s in shipments}
    return sum(by_id[sid]["weighbridge_net_t"] for sid in verified_ids)


def check_c2a(processor_id: str, certified_t: float, verified_inbound_t: float) -> CheckResult:
    """Tolerant on the shortfall fraction (params.C2A_SHORTFALL_TOL), not a
    strict certified <= verified_inbound inequality — independent
    per-shipment weighbridge noise otherwise trips this check with no real
    issue behind it (docs/PROGRESS.md's PWP-08 finding). measured and
    affected_tonnes are always the real certified_t and shortfall, whether
    or not the check passes — this tolerance only changes the status line,
    never agents/scorer.py's verifiable/unverifiable tonnes arithmetic."""
    shortfall = max(0.0, certified_t - verified_inbound_t)
    shortfall_pct = shortfall / certified_t if certified_t > 0 else 0.0
    status = "pass" if shortfall_pct <= params.C2A_SHORTFALL_TOL else "fail"
    return CheckResult(
        check_id="C2a",
        status=status,
        severity="hard",
        measured=certified_t,
        threshold=verified_inbound_t,
        affected_tonnes=shortfall,
        evidence_ids=[],
        explanation=(
            f"{processor_id}: certified tonnes ({certified_t:.2f} t) vs verified inbound "
            f"tonnes ({verified_inbound_t:.2f} t) — shortfall {shortfall:.2f} t "
            f"({shortfall_pct:.2%}), tolerance {params.C2A_SHORTFALL_TOL:.0%}."
        ),
    )


def check_c2b(processor_id: str, output_t: float, verified_inbound_t: float) -> CheckResult:
    yield_limit_t = verified_inbound_t * params.MAX_YIELD_RECYCLER
    if output_t <= yield_limit_t:
        return CheckResult(
            check_id="C2b",
            status="pass",
            severity="soft",
            measured=output_t,
            threshold=yield_limit_t,
            affected_tonnes=0.0,
            evidence_ids=[],
            explanation=(
                f"{processor_id}: recycled output sold ({output_t:.2f} t) does not "
                f"exceed {params.MAX_YIELD_RECYCLER:.0%} of verified inbound tonnes "
                f"({yield_limit_t:.2f} t)."
            ),
        )
    excess = output_t - yield_limit_t
    return CheckResult(
        check_id="C2b",
        status="warn",
        severity="soft",
        measured=output_t,
        threshold=yield_limit_t,
        affected_tonnes=excess,
        evidence_ids=[],
        explanation=(
            f"{processor_id}: recycled output sold ({output_t:.2f} t) exceeds "
            f"{params.MAX_YIELD_RECYCLER:.0%} of verified inbound tonnes "
            f"({yield_limit_t:.2f} t) by {excess:.2f} t — suggests material not from "
            "verified waste."
        ),
    )
