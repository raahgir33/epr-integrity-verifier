"""C2a (input balance) and C2b (output plausibility). docs/DATA_SPEC.md §4,
§4a. Applicability (C2b is recycler-only) is runner.py's job, not this
module's — these functions assume they are only called where they apply.
"""

from app.checks import params
from app.checks.consistency import shipment_passes_c4
from app.checks.duplicates import shipment_passes_c5
from app.checks.transport import shipment_passes_c3a, shipment_passes_c3b
from app.models.checks import CheckResult


def verified_inbound_tonnes(shipments: list[dict], duplicate_keys: dict[str, dict]) -> float:
    """docs/DATA_SPEC.md §4a.1: sum of weighbridge net tonnes of matched
    shipments that pass C3, C4 and C5 — the checks-only definition (minus
    a confirmed agent finding is T10's addition, not this function's).

    A shipment missing a field a check needs (shipment_passes_c3a etc.
    returning None) is treated as not failing that check, not as failing
    it: a matched shipment always carries the fields its own matching
    required (vehicle number, time window, quantities), so None here would
    mean a genuine data gap unrelated to the check itself, not grounds to
    zero out tonnes that were otherwise physically evidenced.

    Shared by check_c2a (below) and agents/scorer.py, so the definition of
    "verified" lives in exactly one place.
    """
    total = 0.0
    for s in shipments:
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
        net_t = s.get("weighbridge_net_t")
        if net_t is not None:
            total += net_t
    return total


def check_c2a(processor_id: str, certified_t: float, verified_inbound_t: float) -> CheckResult:
    if certified_t <= verified_inbound_t:
        return CheckResult(
            check_id="C2a",
            status="pass",
            severity="hard",
            measured=certified_t,
            threshold=verified_inbound_t,
            affected_tonnes=0.0,
            evidence_ids=[],
            explanation=(
                f"{processor_id}: certified tonnes ({certified_t:.2f} t) do not exceed "
                f"verified inbound tonnes ({verified_inbound_t:.2f} t)."
            ),
        )
    shortfall = certified_t - verified_inbound_t
    return CheckResult(
        check_id="C2a",
        status="fail",
        severity="hard",
        measured=certified_t,
        threshold=verified_inbound_t,
        affected_tonnes=shortfall,
        evidence_ids=[],
        explanation=(
            f"{processor_id}: certified tonnes ({certified_t:.2f} t) exceed verified "
            f"inbound tonnes ({verified_inbound_t:.2f} t) by {shortfall:.2f} t."
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
