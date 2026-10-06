"""C5 — duplicates. docs/DATA_SPEC.md §4: an e-way bill number, a
weighbridge ticket number, or an (invoice number, supplier GSTIN) pair
appearing more than once, within one processor or across processors.

Keys are document content only — never an internal doc_id/shipment_id,
which can never collide by construction and would hide the real-world
collision this check exists to catch.

Attribution: within a group that shares a key, a mix of matched and
unmatched shipments means only the unmatched side lacks physical evidence
(a weighbridge slip) to back its claim, so only the unmatched members fail.
A group that is entirely matched, or entirely unmatched, is genuinely
ambiguous — there is no evidence to single anyone out — so every member of
it fails.

find_duplicate_keys must be called with every shipment row for exactly one
(seed, facts_source) scope (C5 is explicitly cross-processor, but truth and
extracted rows of the same shipment must never be grouped together).
"""

from app.models.checks import CheckResult


def _ewb_key(s: dict) -> str | None:
    value = s.get("ewb_no")
    return value.strip().upper() if value else None


def _weighbridge_ticket_key(s: dict) -> str | None:
    value = s.get("weighbridge_ticket_no")
    return value.strip().upper() if value else None


def _invoice_gstin_key(s: dict) -> tuple[str, str] | None:
    invoice_no = s.get("invoice_no")
    supplier_gstin = s.get("supplier_gstin")
    if not invoice_no or not supplier_gstin:
        return None
    return (invoice_no.strip().upper(), supplier_gstin.strip().upper())


_KEY_FNS = {
    "ewb_no": _ewb_key,
    "weighbridge_ticket_no": _weighbridge_ticket_key,
    "invoice_no+supplier_gstin": _invoice_gstin_key,
}


def _groups_sharing_a_key(shipments: list[dict], key_fn) -> list[list[dict]]:
    groups: dict[object, list[dict]] = {}
    for s in shipments:
        key = key_fn(s)
        if key is None:
            continue
        groups.setdefault(key, []).append(s)
    return [group for group in groups.values() if len(group) > 1]


def _flagged_members(group: list[dict]) -> list[dict]:
    matched = [s for s in group if s.get("match_status") == "matched"]
    unmatched = [s for s in group if s.get("match_status") != "matched"]
    if matched and unmatched:
        return unmatched
    return group


def _evidence_doc_ids(group: list[dict]) -> list[str]:
    doc_ids = []
    for s in group:
        for doc_id in (s.get("invoice_doc_id"), s.get("eway_doc_id"), s.get("weighbridge_doc_id")):
            if doc_id and doc_id not in doc_ids:
                doc_ids.append(doc_id)
    return doc_ids


def find_duplicate_keys(shipments: list[dict]) -> dict[str, dict]:
    """Returns {shipment_id: {"keys": [...], "evidence_ids": [...]}} for
    every shipment that fails C5. A shipment absent from this dict passes.
    A shipment present in more than one duplicate group has all tripped
    key names and all siblings' evidence merged into one entry.
    """
    flagged: dict[str, dict] = {}
    for key_name, key_fn in _KEY_FNS.items():
        for group in _groups_sharing_a_key(shipments, key_fn):
            evidence = _evidence_doc_ids(group)
            for member in _flagged_members(group):
                entry = flagged.setdefault(member["shipment_id"], {"keys": [], "evidence_ids": []})
                if key_name not in entry["keys"]:
                    entry["keys"].append(key_name)
                for doc_id in evidence:
                    if doc_id not in entry["evidence_ids"]:
                        entry["evidence_ids"].append(doc_id)
    return flagged


def shipment_passes_c5(shipment_id: str, duplicate_keys: dict[str, dict]) -> bool:
    return shipment_id not in duplicate_keys


def check_c5(
    processor_id: str, shipments: list[dict], duplicate_keys: dict[str, dict]
) -> CheckResult:
    """shipments: this processor's rows only, for reporting. duplicate_keys
    must already be computed across every processor's rows in this
    (seed, facts_source) scope — see find_duplicate_keys.
    """
    flagged = [s for s in shipments if s["shipment_id"] in duplicate_keys]
    if not flagged:
        return CheckResult(
            check_id="C5",
            status="pass",
            severity="hard",
            affected_tonnes=0.0,
            evidence_ids=[],
            explanation="No duplicate e-way bill numbers, weighbridge ticket numbers "
            "or (invoice number, supplier GSTIN) pairs.",
        )

    affected_tonnes = sum(s.get("weighbridge_net_t") or 0.0 for s in flagged)
    evidence_ids: list[str] = []
    tripped_keys: list[str] = []
    for s in flagged:
        entry = duplicate_keys[s["shipment_id"]]
        for doc_id in entry["evidence_ids"]:
            if doc_id not in evidence_ids:
                evidence_ids.append(doc_id)
        for key_name in entry["keys"]:
            if key_name not in tripped_keys:
                tripped_keys.append(key_name)

    return CheckResult(
        check_id="C5",
        status="fail",
        severity="hard",
        affected_tonnes=affected_tonnes,
        evidence_ids=sorted(evidence_ids),
        explanation=(
            f"{len(flagged)} shipment(s) for {processor_id} share a duplicate key "
            f"with another shipment: {', '.join(sorted(tripped_keys))}."
        ),
    )
