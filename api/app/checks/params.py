"""All check thresholds. Every value here is cited to docs/DATA_SPEC.md §4
("Rule-derived") or marked ASSUMPTION, matching that table exactly. No
threshold used by checks/ lives anywhere else.
"""

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
