# Data Specification

All data in this project is synthetic. Every document carries a `SYNTHETIC — DEMO DATA` watermark. All entities are fictional; GSTINs use a deliberately invalid checksum.

## 1. Domain facts (verified; cite these, do not invent others)

| Fact | Source |
|---|---|
| Plastic packaging categories: **I** rigid; **II** flexible single or multilayer (different plastics), sheets, carry bags, sachets, pouches; **III** multilayered (at least one plastic and one non-plastic layer); **IV** compostable plastic sheets and carry bags. | CPCB, *FAQs – Centralized EPR Portal for Plastic Packaging* (eprplastic.cpcb.gov.in/plastic/downloads/FAQs.pdf) |
| Plastic Waste Processor types: recyclers, co-processors (waste to energy), waste-to-oil, industrial composting. | Same |
| EPR certificates are generated from the quantity of plastic processed; PIBOs fulfil obligations by acquiring certificates. | Same |
| CSE (Oct 2024): ~700,000 fake certificates, 38× recyclers' generation capacity; end-of-life processors claimed 335.4 Mt/yr against 11.4 Mt/yr capacity; CPCB fines of ₹355 crore. | Down To Earth, reporting the CSE assessment, 29 Oct 2024 |
| E-way bill validity for regular cargo: 1 day per 200 km (or part), expiring at midnight of the last day. Required above ₹50,000 consignment value (interstate). | ClearTax, *E-Way Bill under GST* |
| Open Buildings v3: building polygons for South Asia including India, with `area_in_meters` and `confidence` (0.65–1.0), from 50 cm imagery processed in 2023, CC-BY-4.0. | Earth Engine catalog, `GOOGLE/Research/open-buildings/v3/polygons` |
| HSN 3915: waste, parings and scrap, of plastics (3915 10: of polymers of ethylene). HSN 3901: polymers of ethylene, in primary forms (virgin resin). | Customs tariff Chapter 39, as summarised by ClearTax and others |

Anything not in this table that the code relies on is an **assumption** and must be labelled as such in `params.py` and on the `/method` page.

## 2. Synthetic world

- **Period:** FY 2025-26 (April 2025 – March 2026), monthly granularity.
- **Processors:** 10 fictional PWPs. 8 recyclers (categories I and II), 2 end-of-life processors (co-processing).
- **Brands:** 3 fictional PIBOs. Each holds certificates from several processors, so the portfolio view shows a mix.
- **Suppliers:** 25 fictional aggregators across nearby states, with coordinates.
- **Suppliers master (`suppliers.json`):** fictional aggregators with GSTIN, PIN code and coordinates. Loaded into BigQuery so normalisation can compute straight-line distances without any external geocoding.
- **Sites:** each processor has coordinates. Clean processors are placed inside established industrial areas with visible building footprints; the ghost-site case (F5) is placed on open land. Locations are illustrative; no real business is named or implied. The UI shows coordinates rounded to 2 decimal places only. Record the chosen coordinates and the reason in `ground_truth.json`.
- **Demo batches (`demo_batches.json`):** one scripted "new certificate batch" per processor for the live event demo. For at least one processor with issues, the batch pushes cumulative certified tonnes past verifiable tonnes, so the alert fires on camera.
- **Two seeds:** `--seed 42` is the development set (used to build and tune). `--seed 7` is the held-out test set, generated only after parameters are frozen (T14). Reported metrics come from seed 7.

**Per-shipment realism (T10 fix, 2026-10-07; `api/scripts/dossier_gen/world.py`/`shipments.py`):** the original generator divided a whole year's target tonnage across only ~9–14 shipments while modelling each as one vehicle's one trip — physically impossible net weights (260–1,370 t) on every processor, confirmed by the T10 agent loop's first real run (`docs/PROGRESS.md`). Fixed:
- **Vehicle classes** (`ASSUMPTION` — approximate Indian commercial goods-vehicle GVW/payload bands, not a specific dated regulatory citation): `light_2axle` (net 7–9 t, tare 4,000–6,000 kg) and `heavy_multiaxle` (net 15–25 t, tare 7,000–10,000 kg). Shipment count and the class mix are solved together per processor so the realistic total stays safely under its C1 capacity ceiling (`_shipment_plan` in `shipments.py`).
- **GSTIN state codes** (`STATE_GSTIN_CODE` in `world.py`): the existing 7 real GST state codes already in `gstin.py`, plus Delhi (07) and Uttar Pradesh (09) for supplier-anchor-only states — all real, public GST Council codes.
- **PIN codes** (`PIN_PREFIX` in `world.py`): each of the 25 supplier anchor cities' and 10 processors' real 3-digit India Post PIN prefix, web-search-verified against public sources (bankbazaar.com / indiatvnews.com city PIN-code pages), not guessed. Each processor's city is the one already named in its `site_coordinates.json` note.
- **Distance** (`haversine_km` in `shipments.py`): `distance_km = great_circle(supplier, processor) × ROAD_FACTOR × jitter`, replacing a distance independent of which supplier was actually drawn. Non-H2 shipments draw suppliers from the processor's own state only (real waste aggregation is regional) and exclude suppliers closer than 25 km (a real but very short hop would otherwise let e-way-bill/weighbridge timestamps' 1-minute print precision swing the *recomputed* transit speed past `MAX_AVG_SPEED_KMPH`, even though the true sub-minute speed never does). H2 (the long-haul hard negative) is assigned to a specific real supplier (Alwar) whose distance already lands close to 900 km.
- **End-of-life item descriptions** (`_EOL_DESCRIPTIONS_EN/HI` in `shipments.py`): category III/IV-appropriate wording for PWP-09/PWP-10's normal shipments — fixes a universal, unintentional category mismatch (every shipment previously used recycler-oriented category I/II wording regardless of what the processor is actually permitted to handle). F6's own deliberate one-month certificate-level category breach is untouched.
- **Invoice rate**: `₹8–18/kg`, unchanged in value but now explicitly labelled `ASSUMPTION` in `shipments.py` (no prior citation existed).

Realism enforced by `tests/test_generator_realism.py` (seeds 1–20 excl. 7; every clean/H1–H4 shipment — F2/F3/F8/F4-duplicate are deliberately divergent and excluded).

## 3. Documents per processor

| Type | Format | Count per processor | Key fields to extract |
|---|---|---|---|
| Consent to Operate (CTO) | PDF | 1 | Consent no., processor name, address, permitted categories, capacity (t/yr), valid from, valid to |
| EPR registration certificate | PDF | 1 | Registration no., processor type, categories, capacity |
| Inbound GST tax invoice (from aggregator) | PDF | ~15–25 (T10 realism fix, 2026-10-07: each invoice is one real vehicle's one trip — see §2 — so count tracks capacity rather than the pre-fix fixed 8–14) | Invoice no., date, supplier GSTIN, buyer GSTIN, item description, HSN, quantity (t), rate, value |
| E-way bill | PDF | one per inbound invoice | EWB no., generated at (datetime), valid until, from/to GSTIN, from/to PIN, distance (km), vehicle no., HSN, quantity, value, invoice no. |
| Weighbridge slip | PNG (photo-like: slight rotation, noise, uneven light) | one per inbound invoice | Ticket no., vehicle no., gross, tare, net (kg), in time, out time, remarks |
| Outbound sales invoice (recycled granules or flakes) | PDF | 4–8 | Invoice no., date, buyer, item description, HSN, quantity (t) |
| Electricity bill | PDF | 12 (monthly) | Billing month, units consumed (kWh), connected load |

Target total: ~700 documents across all 10 processors (measured 689–729 across dev seeds 1–20 post-realism-fix; was ~400–500 pre-fix with the old 8–14-invoice count — the realism fix increases shipment count per processor since each is now a single realistic vehicle load, not a large artificial batch). Around 10% use Hindi labels (Devanagari) for field names, rendered with Noto Sans Devanagari. Hindi documents are a stretch goal; if they slow Day 1, drop them.

**How documents are rendered:** Jinja2 HTML templates (one per document type, in `api/scripts/templates/`) rendered to PDF with headless Chromium via Playwright. Weighbridge slips are rendered to PNG the same way, then degraded with Pillow (rotation ±3°, noise, uneven brightness) to look photographed. Chromium shapes Devanagari correctly; ReportLab does not reliably.

**Field formats as printed** (the extractor must cope with these, and `units.py` must parse them): quantities in tonnes on invoices and e-way bills, in kg on weighbridge slips; Indian digit grouping (`1,23,450.00`); dates as `DD/MM/YYYY` and `DD-MM-YYYY HH:MM`; all times IST.

**Inbound invoice item lines** carry an item description and an HSN code. Normal lines are post-consumer waste under HSN 3915. F8 lines (§5) keep HSN 3915 but describe virgin material in words.

**Weighbridge slips** carry a free-text remarks field (mostly blank or routine, e.g. "moisture deduction 1%").

Certificates are not documents: they are a structured ledger (`certificates.csv`) mirroring a portal export: certificate ID, processor, brand, category, quantity (t), generation date, period month.

## 4. Deterministic checks and parameters

Every parameter below goes in `api/app/checks/params.py` with the label shown.

EPR certificates are generated on the quantity of plastic waste **processed (input)**, not on recycled output. The checks follow that.

All capacity and mass-balance checks are **cumulative over the financial year to date**, evaluated at each month end. This avoids false positives from normal month-to-month timing (stock carried over, a shutdown month).

| ID | Check | Rule | Parameters | Label |
|---|---|---|---|---|
| C1 | Capacity | FY-to-date certified tonnes ≤ CTO capacity (t/yr) × months elapsed / 12 | none | Rule-derived |
| C2a | Input balance | FY-to-date certified tonnes within tolerance of FY-to-date verified inbound waste tonnes (weighbridge net of shipments that pass C3–C5): (certified − verified inbound) / certified ≤ tolerance | `C2A_SHORTFALL_TOL = 0.02` | ASSUMPTION |
| C2b | Output plausibility | FY-to-date recycled output sold ≤ FY-to-date processed tonnes × max yield. Excess output suggests material not from waste | `MAX_YIELD_RECYCLER = 0.95` | ASSUMPTION, soft signal |
| C3a | Transit speed | Distance ÷ (weighbridge in-time − e-way bill generation time) ≤ max speed. Distance = declared e-way bill distance; if missing, straight-line × road factor using supplier and site coordinates | `ROAD_FACTOR = 1.3`, `MAX_AVG_SPEED_KMPH = 55` | ASSUMPTION |
| C3b | E-way bill validity | Weighbridge in-time ≤ valid-until (1 day per 200 km or part, ending 23:59:59 IST) | `EWB_KM_PER_DAY = 200` | Rule-derived |
| C4 | Consistency | Invoice qty vs e-way bill qty within tolerance; weighbridge net vs invoice qty within tolerance; vehicle no. and GSTINs match | `QTY_TOL_DOC = 0.01`, `QTY_TOL_WEIGHBRIDGE = 0.02` | ASSUMPTION |
| C5 | Duplicates | An e-way bill number, a weighbridge ticket number, or an (invoice number, supplier GSTIN) pair appears more than once, **within one processor or across processors** | none | Rule-derived |
| C6 | Consent | Processing dates within CTO validity; certificate category within permitted categories | none | Rule-derived |
| C7 | Energy | kWh per processed tonne within plausible band; months with processing but near-zero consumption flagged | `KWH_PER_T_MIN = 150`, `KWH_PER_T_MAX = 1200` | ASSUMPTION, soft signal |
| C8 | Site | Total building footprint within `SITE_RADIUS_M` of registered coordinates; claimed capacity per m² of footprint ≤ ceiling; no buildings is a strong signal | `SITE_RADIUS_M = 150`, `MIN_BUILDING_CONFIDENCE = 0.75`, `MAX_TPA_PER_M2 = 10` | ASSUMPTION, soft signal |

**Applicability by processor type** (a check that does not apply returns `not_evaluable`, never `pass`):

| Check | Recycler | End-of-life (co-processing) |
|---|---|---|
| C1, C2a, C3, C4, C5, C6, C8 | Yes | Yes |
| C2b output plausibility | Yes | No (no recycled product) |
| C7 energy | Yes | No (kiln energy is not plastic-driven) |

**Shipment matching rules** (in `normalize.py`):
1. Invoice ↔ e-way bill: by invoice number printed on the e-way bill, plus supplier GSTIN.
2. E-way bill ↔ weighbridge slip: same vehicle number, weighbridge in-time after e-way bill generation and before valid-until + 3 days; the earliest such slip wins. A slip matched to two e-way bills is a C5 finding.
3. Anything unmatched is kept with `match_status = unmatched` and contributes zero verified tonnes.

## 4a. Verifiable tonnes and risk band (computed in `agents/scorer.py`, deterministic)

For each processor, financial year to date:

1. **Verified inbound tonnes** = Σ weighbridge net tonnes of matched shipments that pass C3, C4 and C5, **minus** shipments cited by an agent finding both agents agree on (the Hypothesis/Critic agreement rule below) that is also "deductible" (for example F8: material described as virgin) — see the own-evidence rule and the systemic-finding guard below for agreed findings excluded from this deduction.
2. **Capacity limit** = CTO capacity × months elapsed / 12, set to 0 for months outside CTO validity (C6).
3. **Verifiable tonnes** = min(eligible certified tonnes, verified inbound tonnes, capacity limit), where eligible certified tonnes excludes certificates in a category the CTO does not permit (C6) — that activity is out of consent no matter how well-backed physically, so it is excluded from the basis the minimum is taken over, not just flagged in the risk band.
4. **Unverifiable tonnes** = certified tonnes (the full figure, not the eligible subset from step 3) − verifiable tonnes.
5. **Risk band** from unverifiable share: Low < 5%, Medium 5–25%, High > 25%. Each failed soft signal (C2b, C7, C8) or a non-empty own-evidence, systemic-finding or disputed-finding list (all below) raises the band by one step, at most one step in total — never more than one, regardless of how many of these signals fire together.

**Objection-direction rule (T10, decided 2026-10-07):** every Critic objection carries `effect`, `"raises_concern"` or `"resolves_concern"` — the Critic must say whether it is identifying a problem or correcting an earlier Hypothesis conclusion that reads as over-harsh given the evidence. Only `raises_concern` objections become candidate findings (ID-validated, subject to the agreement rule below, scored/deducted, shown as findings in the UI); `resolves_concern` objections never do — they are filtered out immediately after the Critic's final call. The Critic's full raw response, both kinds of objection together, is logged to the agent trail *before* that filtering, so a `resolves_concern` objection still stays visible there as a correction, never silently discarded. Implemented in `app/models/agent.py`'s `Objection.effect` (required, no default — the Critic must always say which) and `app/agents/orchestrator.py`'s `run_agent_loop` (the `objections`/`hypothesis_findings` filters, right after each trail step is logged). The same `effect` field and filter apply to the Hypothesis's own proposed findings below, not only the Critic's.

**Hypothesis/Critic agreement rule (T10, decided 2026-10-08):** the Hypothesis proposes findings of its own now, not only batch-level conclusions — same shape as a Critic finding (`finding_type`, `effect`, `cited_shipment_ids`, `evidence_ids`, `explanation`). A finding only becomes a candidate for deduction once **both agents agree on it**:
- A **Hypothesis finding** is agreed only if the Critic actively gives it an `"upheld"` verdict. Silence (no verdict at all) is *not* agreement — a Hypothesis finding the Critic never addressed needs an explicit response from the Hypothesis just like a disputed one does (below); treating silence as agreement would let the Hypothesis's own self-assessment stand uncontested. A `"disputed"` verdict (or no verdict at all) puts the finding up for one revision round: the Hypothesis decides `"maintain"` (still stands — becomes a **review flag**, kept visible but never deducted) or `"withdraw"` (the finding disappears entirely — **trail-only**, no scoring effect, not even a review flag). A disputed-or-unaddressed finding the Hypothesis itself never responds to also defaults to a review flag, never to silent confirmation or silent disposal — only an *explicit* withdrawal makes a finding vanish.
- A **Critic-raised finding** (the pre-existing `objections` path) keeps its prior default: agreed unless the Hypothesis explicitly `rejects` it in the one revision round (silence = accepted, since the Critic's skepticism is the actual check here — not pushing back when given the one chance to means the finding stands). Reworked from the original design: a **rejected** Critic finding is now a **review flag** (kept, visible, not deducted) rather than fully discarded, so a confirmed disagreement between the agents stays visible instead of vanishing without a trace.

Review-flagged findings (both origins) ride a third synthetic soft-signal `CheckResult` into step 5's one-step risk-band bump (`check_id="AGENT_DISPUTED_FINDING"`), same mechanism as the own-evidence and systemic-finding signals below. Implemented in `app/agents/orchestrator.py`'s `run_agent_loop` (the `verdicts`/`hypothesis_finding_responses` handling and the `confirmed_findings`/`review_flag_findings`/`withdrawn_findings` split) and `app/agents/scorer.py`'s `build_disputed_finding_check_result`.

**Own-evidence rule (T10, decided 2026-10-07; reworked 2026-10-08):** a finding's evidence must be **shipment-level only** for any deduction — if even one `evidence_ids` entry isn't one of the three shipment-level document types (invoice, e-way bill, weighbridge slip), the whole finding is processor-level, never partially deductible. "Shipment-level only" rules out an electricity bill, site imagery, a CTO/consent or EPR registration document, an output invoice, or any non-document evidence_id (a `certificate_id`, a site thumbnail path) appearing *anywhere* in that finding's evidence — even alongside otherwise-valid shipment-level evidence. (First version, superseded: a finding was deductible as long as *some* of its evidence matched a cited shipment's own document, regardless of what else was also cited as evidence — satisfiable by attaching a shipment's own invoice *alongside* a processor-level document. PWP-07's real F7 finding did exactly that: it cited shipments and attached their own invoices, but the finding's substance, and its only genuinely supporting evidence, was the electricity bill — the invoices didn't make the finding shipment-level, they just happened to also be cited.) Even with shipment-level-only evidence, **every** cited shipment must have at least one of its own documents among that evidence for the finding to be deductible at all — a finding evidencing some but not all of its cited shipments deducts nothing, not a partial subset. Such a finding is **kept** (visible in `confirmed_findings`, the trail, the UI) but classified `no_evidence` rather than `deductible`: excluded from step 1's deduction, contributing instead to step 5's risk-band bump via a second synthetic soft-signal `CheckResult` (`check_id="AGENT_NO_OWN_EVIDENCE_FINDING"`). Applied *before* the systemic-finding guard below — a finding's share, for that guard's purposes, is computed over its (now all-or-nothing) evidenced shipments, not its full, unfiltered citation list. Implemented in `app/agents/orchestrator.py`'s `_evidenced_shipment_ids`/`_classify_findings` and `app/agents/scorer.py`'s `build_no_own_evidence_finding_check_result`. `critic_final.txt` states this requirement directly ("For every shipment you cite, include at least one of that shipment's own document IDs in evidence_ids"), and the dossier digest (`_build_dossier_digest`) carries each shipment's own document IDs inline so the Critic can satisfy it without a separate tool call.

**Systemic-finding guard (T10, decided 2026-10-07):** of a finding's evidenced shipments (after the own-evidence rule above), citing more than `SYSTEMIC_FINDING_SHARE_THRESHOLD` (0.5, `ASSUMPTION`, `app/checks/params.py`) of the processor's own verified shipments is too broad to treat as ordinary per-shipment evidence — deducting all of them would let one finding zero out most of the processor's verifiable tonnage from a single objection. Such a finding is **kept** (visible in `confirmed_findings`, the agent trail, and the UI) but classified as "systemic" rather than "deductible": it is excluded from step 1's tonnage deduction and instead contributes to step 5's one-step risk-band bump via a synthetic soft-signal `CheckResult` (`check_id="AGENT_SYSTEMIC_FINDING"`). Implemented in `app/agents/orchestrator.py`'s `_classify_findings` (classification) and `app/agents/scorer.py`'s `build_systemic_finding_check_result` (the synthetic check result); the denominator is `app/checks/mass_balance.py`'s `verified_inbound_shipment_ids`, the same C3/C4/C5 predicate `verified_inbound_tonnes` sums, exposed as an ID set. `app/agents/orchestrator.py`'s `_classify_findings` also returns `excluded_shipment_ids` directly — the union of every deductible finding's own evidenced shipment IDs — so callers (`scripts/run_pipeline.py`, `scripts/probe_agent_thinking.py`) pass it straight to `score_processor` rather than re-deriving it from `cited_shipment_ids` themselves.

**Concurs-with-check rule (T10, decided 2026-10-08, checked before the own-evidence/systemic gates above):** a confirmed finding that adds nothing beyond what a deterministic check already caught is classified `concurs_with_check` — kept (visible in `confirmed_findings`, the trail, the UI) but excluded from step 1's deduction *and*, unlike every other classification above, contributing **no** synthetic soft-signal `CheckResult` at all: the check it concurs with already did whatever deduction or bump was warranted, so a second signal for the same thing would double-count. A finding concurs with a check if either (a) every shipment it cites is already excluded from `verified_inbound_shipment_ids` by a hard check, or (b) its `evidence_ids` overlap with a failed-or-warned deterministic check's own `evidence_ids`. Found from the acceptance run (not designed speculatively): a finding citing a shipment that fails C4 (weighbridge net materially below invoice quantity) with that same shipment's own documents as evidence was indistinguishable, under the prior rules, from a genuinely new F8-style finding — it was classified `deductible` (redundant with C4's own exclusion, since a check-failing shipment was never in `verified_inbound_t` to begin with, so no tonnage double-counting resulted, but it still counted as a false F8 citation in the eval metric) or `no_evidence` (adding a redundant soft-signal bump on top of the check's own C4/C5/C7/C8 bump — PWP-10's F4 finding did exactly this, producing an inconsistent Medium-vs-Low risk band between two otherwise-identical acceptance runs). Alongside this, **cited-ID validation (`_filter_objection`) now filters `cited_shipment_ids` against `verified_inbound_shipment_ids`, not merely "exists in this processor's shipments"** — a shipment that's unmatched or already failing a hard check was never counted in verified inbound tonnes, so citing it can't mean anything for deduction; this makes condition (a) above rarely reachable in practice (a non-verified ID is stripped before classification runs at all) — condition (b), the evidence-overlap check, is what actually fires on real data. Implemented in `app/agents/orchestrator.py`'s `_concurs_with_check`/`_classify_findings`/`_filter_objection`. A public `classify_confirmed_findings(confirmed_findings, processor_context)` factors the classification sequence out of `run_agent_loop` so it can be re-run offline against an already-saved run's findings (e.g. after a scoring-rule change) without a new Gemini call — `scripts/probe_agent_thinking.py --rescore <path>` uses this.

The generator computes `true_verifiable_t` with the same definition, applied to the true underlying shipments rather than to extracted documents. That makes the tonnage error metric meaningful.

Each `CheckResult` has: `check_id`, `status` (pass / fail / warn / not_evaluable), `severity` (hard / soft), `measured`, `threshold`, `affected_tonnes`, `evidence_ids` (document or row IDs), `explanation`.

## 5. Seeded issue types

Grounded in documented cases (CSE assessment, CPCB audits).

| ID | Issue | How it is seeded | Caught by |
|---|---|---|---|
| F1 | Capacity inflation | Certificates exceed CTO capacity for several months | C1 |
| F2 | Phantom inbound | Invoices and e-way bills without weighbridge slips; or transit implying > 120 km/h | C2, C3 |
| F3 | Quantity inflation | Weighbridge net materially below invoice quantity | C4, C2 |
| F4 | Double use | The same set of inbound invoices and e-way bills appears in two processors' dossiers (only visible with a cross-processor view) | C5 |
| F5 | Ghost site | Registered coordinates on open land; no building footprint | C8 |
| F6 | Consent breach | Processing after CTO expiry, or certificates in a category the CTO does not permit | C6 |
| F7 | Energy implausibility | Output months with near-zero electricity use | C7 |
| F8 | Semantic contradiction | Inbound invoice lines keep HSN 3915 (waste and scrap) but the description says, in English or Hindi, "virgin LDPE granules", "fresh film rolls, unused" or "प्राइम ग्रेड दाना"; or a weighbridge remark says "same load re-weighed". The codes look compliant; only the words reveal the problem | **Agents only** (no deterministic check) |

**Hard negatives** (clean but unusual, to measure false positives):
- H1 Utilisation at 95% of capacity, within limits.
- H2 Long-haul shipment (~900 km) with plausible timing.
- H3 Quantity differences inside tolerance.
- H4 One month of planned shutdown with zero output and low energy.

**Assignment (10 processors):** 4 clean, 6 with issues. Every F1–F8 appears at least once; F1 appears twice; F8 appears on exactly two processors (one of which carries F8 only, so the agent's unique contribution is measurable — no deterministic check fires there). A soft signal (F5, F7) never stands alone on a processor; it is always paired with a hard issue, since a soft signal alone doesn't reduce verifiable tonnes. F7 and H4 (both energy-related) only land on recyclers, since C7/energy does not apply to end-of-life processors. This needs 10 processor-tags (F1×2 + F2,F3,F4,F5,F6,F7×1 each + F8×2) across 6 issue-processors, so **4 of the 6 carry two issue types and 2 carry one** — not "two processors carry two issue types" as an earlier draft said; that count could not satisfy the other constraints simultaneously.

Fixed assignment:

| Processor | Type | Issue types |
|---|---|---|
| PWP-01 | Recycler | none — clean; also the innocent original holder of the record PWP-10 duplicates for F4 |
| PWP-02 | Recycler | none — clean |
| PWP-03 | Recycler | none — clean; carries H1 + H2 |
| PWP-04 | Recycler | none — clean; carries H3 + H4 |
| PWP-05 | Recycler | F1, F8 |
| PWP-06 | Recycler | F1, F3 |
| PWP-07 | Recycler | F2, F7 |
| PWP-08 | Recycler | F8 (only) |
| PWP-09 | End-of-life | F5, F6 |
| PWP-10 | End-of-life | F4 |

**F4 mechanics:** PWP-10's dossier contains a copy of one of PWP-01's real inbound invoice + e-way-bill records (same invoice no., supplier GSTIN, EWB number) but with no matching weighbridge slip on PWP-10's side — so C5 (and the fact that it's unmatched) attributes the duplicate to PWP-10, while PWP-01's original, properly matched shipment stays clean. (An earlier draft also seeded "one weighbridge ticket reused within a dossier" on PWP-10; dropped — that would require truth-mode normalisation to encode a match that `normalize.py`'s real extracted-mode matching rules, operating on vehicle number and time window, could never independently derive from the copied e-way bill, which would make truth and extracted modes permanently disagree on this shipment.)

**Certified-tonnage basis:** for every processor *without* F1, F2 or F3 (clean, H1–H4, F4–F8), certificates are derived per month from that month's actual verified weighbridge net, rounded down — honest practice, certify on what was weighed. Electricity use for these processors is likewise drawn from the same month's actual weighbridge net, so the two stay consistent even though real shipments land unevenly across months. F1/F2/F3 processors keep certificates (and, for F1, electricity) on an independent capacity-ratio formula, since their entire premise is a certified-vs-verified mismatch (F1 against capacity; F2/F3 against verified inbound) — deriving their certified figure from the same weighed total it is supposed to diverge from would erase the issue. An earlier version computed every processor's certified tonnage independently of its actual shipments; purely by chance (±10% per-shipment invoice-quantity draws, summed over only 8–14 shipments) this could leave a clean processor's certified tonnage several percent short of its weighed total, intermittently and falsely failing C2a — see `docs/PROGRESS.md`'s diagnosis and the generator-level robustness test (`tests/test_c2a_noise_robustness.py`) that now guards against a regression.

## 6. Ground truth file (`data/synthetic/ground_truth.json`)

```json
{
  "seed": 42,
  "processors": [
    {
      "processor_id": "PWP-03",
      "label": "issues",
      "issue_types": ["F1", "F8"],
      "hard_negatives": [],
      "certified_t": 4200.0,
      "true_verifiable_t": 2650.0,
      "affected_certificate_ids": ["CERT-03-0007", "..."],
      "site": { "lat": 0.0, "lon": 0.0, "placement_note": "industrial area" }
    }
  ],
  "documents": [
    { "doc_id": "PWP-03-INV-004", "doc_type": "inbound_invoice", "fields": { "invoice_no": "...", "quantity_t": 18.4 } }
  ]
}
```

## 7. Evaluation (`scripts/run_eval.py` → `eval_results`, shown on `/evaluation`)

| Metric | Definition |
|---|---|
| Extraction field accuracy | Share of key fields (quantities, dates, document numbers, GSTINs, vehicle numbers) correct after parsing both the extracted and the true value with `units.py`, by document type and overall; Hindi documents and weighbridge photos reported separately |
| Processor-level detection | Precision, recall, F1 for "has issues" vs ground truth |
| Issue-type recall | Share of seeded F1–F8 instances detected, per type |
| False positives on hard negatives | Count of H1–H4 processors wrongly flagged |
| Tonnage error | Mean absolute error between computed and true verifiable tonnes |
| **Agent contribution** | The same metrics for **checks only** vs **checks + agents**. F8 recall is the clearest measure |
| **Extraction impact** | Processor-level metrics with `--facts-source truth` vs `extracted`. Shows how much end-to-end accuracy depends on reading documents correctly |
| **Run-to-run stability** | Agent stage run twice on the test set; share of processors whose risk band is identical |

**Cited-shipment scoring rule (T10, decided 2026-10-07):** a confirmed agent finding's `cited_shipment_ids` are scored against ground truth's `is_f8` flag for precision/recall, **except** on a processor whose seeded issue includes F5 (ghost site) — F5 has no shipment-level manifestation (it is a site-level finding, caught by C8), so any shipment citation the agent produces on that processor is excluded from the precision/recall denominator entirely: neither a true positive nor a false positive. Without this exclusion, a correct non-F8 finding on the F5 processor (for example, F6's category mismatch, which does cite shipments) would be wrongly counted as a false F8 citation. Implemented in `scripts/probe_agent_thinking.py`'s `compute_run_metrics`.

**Objection-direction and own-evidence rules don't change this metric's denominator, only its inputs (T10, decided 2026-10-07):** `confirmed_findings` (what `compute_run_metrics` reads `cited_shipment_ids` from) already excludes every `resolves_concern` objection — §4a's objection-direction rule filters those out before an objection can become a finding at all, so they were never candidates for this metric either; no separate exclusion is needed here. The own-evidence rule is deliberately **not** applied to this metric: a finding classified `no_evidence` (§4a) still contributes its full `cited_shipment_ids` to precision/recall here, because citation accuracy (did the agent point at the right shipments) and deduction eligibility (can this evidence support subtracting their tonnage) are different questions — a citation can be exactly right about *which* shipments an issue affects while still resting on only processor-level evidence, and the eval metric should credit that even though scoring won't deduct for it.

**F7's narrower version of the same rule (T10, decided 2026-10-07):** a processor's F7 (energy implausibility) month likewise has no shipment-level manifestation — it is a monthly electricity-bill figure, caught by C7 — so a citation of a shipment that falls in that processor's own seeded F7 month is neutral too, exactly like F5. Unlike F5, this exclusion is **per-month, not per-processor**: F7 doesn't invalidate every other month's citation-worthiness (for example PWP-07 also carries F2, whose phantom-inbound shipments are still fair game for the metric). The target month is found from the data itself — the month with minimum `kwh` in that processor's own `energy_monthly` — not by re-deriving the generator's own month-selection logic. Implemented in `scripts/probe_agent_thinking.py`'s `_f7_neutral_shipment_ids` and `compute_run_metrics`.

**Concurs-with-check findings are excluded from this metric too (T10, decided 2026-10-08):** `compute_run_metrics`'s `_cited_shipment_ids` reads from `confirmed_findings`, same as always, but now excludes any finding also present in `concurs_with_check_findings` (§4a) — a finding that only restates what a deterministic check already caught is neither a true nor a false F8 citation, the same neutral treatment the F5/F7 exclusions above already get. This directly fixed the acceptance run's only two false F8 citations (PWP-06's C4-concurrence, PWP-10's C5-concurrence on the F4 duplicate) — both were genuinely correct observations, just not new ones, and the metric had no prior way to credit "restates a check" differently from "a genuinely new finding." Re-scoring both saved acceptance runs offline under this fix (no new Gemini calls) took overall F1 from 0.667/0.800 to a clean 1.000/1.000 in both runs, with recall unchanged (F8 was already fully caught).

**Protocol:** all parameters in `params.py` and all prompts are frozen (tagged commit) before the seed-7 test set is generated. Reported numbers come from seed 7 only. Seed-42 numbers may be shown as "development set", clearly labelled.

Report all metrics honestly, including weak ones. The `/evaluation` page states that the test set is synthetic and seeded from documented issue types.
