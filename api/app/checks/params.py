"""All check thresholds. Every value here is cited to docs/DATA_SPEC.md §4
("Rule-derived") or marked ASSUMPTION, matching that table exactly. No
threshold used by checks/ lives anywhere else.
"""

# C2a (input balance) — ASSUMPTION, aligned with QTY_TOL_WEIGHBRIDGE below.
# Certified tonnes may exceed verified inbound tonnes by this fraction of
# certified tonnes before C2a fails — independent per-shipment weighbridge
# noise (+/-0.5% in this dataset) accumulates across a processor's
# shipments and can otherwise trip a strict inequality with no real issue
# behind it (see docs/PROGRESS.md's PWP-08 finding). Does not change the
# verifiable/unverifiable tonnes arithmetic (agents/scorer.py) — only this
# check's own pass/fail line.
C2A_SHORTFALL_TOL = 0.02

# C2b (output plausibility) — ASSUMPTION, soft signal. Recycled output sold
# must not exceed processed tonnes times this yield ceiling.
MAX_YIELD_RECYCLER = 0.95

# C3a (transit speed) — ASSUMPTION. Straight-line fallback (used only when
# an e-way bill's distance_km is missing — not exercised by this dataset,
# see docs/PROGRESS.md) multiplies supplier-to-site straight-line distance
# by this road-detour factor.
ROAD_FACTOR = 1.3

# C3a (transit speed) — ASSUMPTION. Distance / transit time must not exceed
# this average speed.
MAX_AVG_SPEED_KMPH = 55

# C3b (e-way bill validity) — Rule-derived (GST e-way bill rule: 1 day of
# validity per 200 km or part thereof). The generator already bakes this
# formula into each e-way bill's printed valid_until (see
# scripts/dossier_gen/shipments.py's ewb_valid_days); C3b itself compares
# weighbridge in-time directly against that printed field, so this
# constant is not recomputed at check time — it is recorded here because
# docs/DATA_SPEC.md §4 lists it as C3b's parameter.
EWB_KM_PER_DAY = 200

# C4 (consistency) — ASSUMPTION. Invoice quantity vs e-way bill quantity
# tolerance (fractional).
QTY_TOL_DOC = 0.01

# C4 (consistency) — ASSUMPTION. Weighbridge net vs invoice quantity
# tolerance (fractional).
QTY_TOL_WEIGHBRIDGE = 0.02

# C7 (energy) — ASSUMPTION, soft signal. Plausible kWh-per-tonne band for a
# recycler; outside this range (in either direction) is implausible.
KWH_PER_T_MIN = 150
KWH_PER_T_MAX = 1200

# C8 (site) — ASSUMPTION, soft signal. Open Buildings polygons within this
# radius (metres) of the registered coordinates count toward the site's
# footprint.
SITE_RADIUS_M = 150

# C8 (site) — ASSUMPTION. Open Buildings v3 polygons below this confidence
# are excluded from the footprint.
MIN_BUILDING_CONFIDENCE = 0.75

# C8 (site) — ASSUMPTION, soft signal. Claimed capacity per m² of building
# footprint must not exceed this ceiling.
MAX_TPA_PER_M2 = 10

# C8 (site) — imagery window for geo/site.py's Sentinel-2 composite and
# the Open Buildings overlay it's painted onto. Fixed to match Open
# Buildings v3's own 2023 imagery vintage, not a rolling "last 12 months"
# — a rolling window would risk showing buildings constructed or
# demolished since the 2023 snapshot that the footprint data itself can't
# confirm either way.
S2_DATE_START = "2023-01-01"
S2_DATE_END = "2023-12-31"

# Agent loop (docs/ARCHITECTURE.md §4) — Rule-derived (architecture spec):
# "maximum 8 tool calls per Critic run."
AGENT_MAX_TOOL_CALLS = 8
# Per-run timeout — raised from 180s to 300s, 2026-10-08 (docs/PROGRESS.md,
# developer decision after the fifth canary): PWP-08's own total wall-clock
# through just the Hypothesis+Critic tool-loop phase was 282.2s in the run
# that hit an intermittent ~120s-class backend stall on agent_critic_tools
# (confirmed server-side — see app/llm.py/app/config.py). Paired with the
# fail-fast approach (app/config.py's per-purpose agent_*_timeout_ms
# settings; app/llm.py's _agent_max_attempts — 3 for agent_hypothesis, 4
# for the critic-phase purposes since 2026-10-08) rather than simply
# waiting longer per attempt. Also paired with a processor-level retry
# (app/agents/orchestrator.py's run_agent_loop_with_retry) that re-runs
# the whole loop once more, with its own fresh AGENT_TIMEOUT_S budget, if
# even that isn't enough — the acceptance pair's own PWP-05 loss was
# exactly this budget being exhausted by three consecutive 504s.
AGENT_TIMEOUT_S = 300

# F7 (energy implausibility seeding) — ASSUMPTION. The generator's F7
# month draws kWh/t from this band — well below KWH_PER_T_MIN (150) so
# C7 still fails, but not so low it reads as a generator artifact rather
# than a plausible (if suspicious) low-energy month. Developer-set
# 2026-10-07 after the first real agent run flagged the previous flat
# 5-30 kWh absolute draw as implausible once per-shipment tonnage became
# realistic (docs/PROGRESS.md).
F7_KWH_PER_T_MIN = 50
F7_KWH_PER_T_MAX = 110

# Agent systemic-finding guard (docs/PROGRESS.md) — ASSUMPTION. A
# confirmed finding citing more than this share of a processor's verified
# shipments is treated as a systemic/UI-review flag rather than a normal
# per-shipment deduction — see app/agents/orchestrator.py.
SYSTEMIC_FINDING_SHARE_THRESHOLD = 0.5

# Clarification memo (app/agents/memo.py) — ASSUMPTION. No regulatory
# deadline governs this administrative step; 15 days is a reasonable
# response window, developer-set.
MEMO_RESPONSE_DEADLINE_DAYS = 15

# Verification statement, Part B (app/agents/memo.py) — ASSUMPTION. A
# passed hard check within this fraction of its own threshold is
# surfaced as an early-warning observation, not a finding.
IMPROVEMENT_NEAR_THRESHOLD_MARGIN = 0.10

# Verification statement, Part B (app/agents/memo.py) — ASSUMPTION. A
# CTO/EPR registration expiring within this many months of the
# assessment month is surfaced as a consent-expiry observation.
CONSENT_EXPIRY_WARNING_MONTHS = 6

# T11 (API): one short source label per check, for the UI's
# "Measured X · Tolerance Y (assumption)" line. Mirrors each check's own
# threshold comment above, not a new judgement — C1/C5/C6 have no tunable
# threshold constant at all (C1's limit is a processor fact, not a
# params.py value; C5/C6 are rule-only, no tolerance), so their label says
# that explicitly rather than pointing at a constant that doesn't exist.
CHECK_SOURCE_LABELS: dict[str, str] = {
    "C1": "Consented capacity (processor-specific fact, not a tunable threshold)",
    "C2a": "ASSUMPTION (C2A_SHORTFALL_TOL)",
    "C2b": "ASSUMPTION (MAX_YIELD_RECYCLER)",
    "C3a": "ASSUMPTION (MAX_AVG_SPEED_KMPH, ROAD_FACTOR)",
    "C3b": "Rule-derived — GST e-way bill rule (EWB_KM_PER_DAY)",
    "C4": "ASSUMPTION (QTY_TOL_DOC, QTY_TOL_WEIGHBRIDGE)",
    "C5": "Rule-derived — document/ticket uniqueness, no tolerance",
    "C6": "Rule-derived — CTO consent dates and permitted categories, no tolerance",
    "C7": "ASSUMPTION (KWH_PER_T_MIN, KWH_PER_T_MAX)",
    "C8": "ASSUMPTION (SITE_RADIUS_M, MIN_BUILDING_CONFIDENCE, MAX_TPA_PER_M2)",
    # Synthetic soft-signal check results the agent loop appends
    # (app/agents/scorer.py) — not one of the deterministic C1-C8 checks.
    "AGENT_SYSTEMIC_FINDING": "ASSUMPTION (SYSTEMIC_FINDING_SHARE_THRESHOLD)",
    "AGENT_NO_OWN_EVIDENCE_FINDING": "Rule-derived — own-evidence rule, no tolerance",
    "AGENT_DISPUTED_FINDING": "Rule-derived — Hypothesis/Critic agreement rule, no tolerance",
}
