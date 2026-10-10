"""Path/query parameter ID patterns (T13.8 hardening).

Each pattern is verified against the real seed-42 dataset, not invented:
`data/synthetic/seed-42/{ground_truth.json,brands.json,demo_batches.json}`.
A request whose path parameter doesn't match returns FastAPI's own 422
before any lookup runs (today's behaviour: 404 only after a cache miss).
"""

# processors.json / every processor_id used throughout the dataset.
PROCESSOR_ID_PATTERN = r"^PWP-\d{2}$"

# brands.json's brand_id field (BRAND-01, BRAND-02, ...).
BRAND_ID_PATTERN = r"^BRAND-\d{2}$"

# Verified against all 714 ground_truth.json doc_ids plus all 6
# demo_batches.json extra_document_ids (zero non-matches): a processor id,
# then one or more hyphen-joined uppercase/digit/underscore segments (the
# document type — EWAY_BILL, ELECTRICITY_BILL, or compound DEMO-prefixed
# ones), then a numeric suffix. e.g. PWP-01-CTO-001,
# PWP-01-ELECTRICITY_BILL-056, PWP-01-DEMO-INBOUND_INVOICE-001.
DOC_ID_PATTERN = r"^PWP-\d{2}(-[A-Z0-9_]+)+-\d+$"
