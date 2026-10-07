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
