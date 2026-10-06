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

## 3. Documents per processor

| Type | Format | Count per processor | Key fields to extract |
|---|---|---|---|
| Consent to Operate (CTO) | PDF | 1 | Consent no., processor name, address, permitted categories, capacity (t/yr), valid from, valid to |
| EPR registration certificate | PDF | 1 | Registration no., processor type, categories, capacity |
| Inbound GST tax invoice (from aggregator) | PDF | 8–14 | Invoice no., date, supplier GSTIN, buyer GSTIN, item description, HSN, quantity (t), rate, value |
| E-way bill | PDF | one per inbound invoice | EWB no., generated at (datetime), valid until, from/to GSTIN, from/to PIN, distance (km), vehicle no., HSN, quantity, value, invoice no. |
| Weighbridge slip | PNG (photo-like: slight rotation, noise, uneven light) | one per inbound invoice | Ticket no., vehicle no., gross, tare, net (kg), in time, out time, remarks |
| Outbound sales invoice (recycled granules or flakes) | PDF | 4–8 | Invoice no., date, buyer, item description, HSN, quantity (t) |
| Electricity bill | PDF | 12 (monthly) | Billing month, units consumed (kWh), connected load |

Target total: ~400 documents. Around 10% use Hindi labels (Devanagari) for field names, rendered with Noto Sans Devanagari. Hindi documents are a stretch goal; if they slow Day 1, drop them.

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
| C2a | Input balance | FY-to-date certified tonnes ≤ FY-to-date verified inbound waste tonnes (weighbridge net of shipments that pass C3–C5) | none | Rule-derived |
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

1. **Verified inbound tonnes** = Σ weighbridge net tonnes of matched shipments that pass C3, C4 and C5, **minus** shipments cited by a confirmed agent finding (for example F8: material described as virgin).
2. **Capacity limit** = CTO capacity × months elapsed / 12, set to 0 for months outside CTO validity (C6).
3. **Verifiable tonnes** = min(certified tonnes, verified inbound tonnes, capacity limit).
4. **Unverifiable tonnes** = certified tonnes − verifiable tonnes.
5. **Risk band** from unverifiable share: Low < 5%, Medium 5–25%, High > 25%. Each failed soft signal (C2b, C7, C8) raises the band by one step, at most one step in total.

The generator computes `true_verifiable_t` with the same definition, applied to the true underlying shipments rather than to extracted documents. That makes the tonnage error metric meaningful.

Each `CheckResult` has: `check_id`, `status` (pass / fail / warn / not_evaluable), `severity` (hard / soft), `measured`, `threshold`, `affected_tonnes`, `evidence_ids` (document or row IDs), `explanation`.

## 5. Seeded issue types

Grounded in documented cases (CSE assessment, CPCB audits).

| ID | Issue | How it is seeded | Caught by |
|---|---|---|---|
| F1 | Capacity inflation | Certificates exceed CTO capacity for several months | C1 |
| F2 | Phantom inbound | Invoices and e-way bills without weighbridge slips; or transit implying > 120 km/h | C2, C3 |
| F3 | Quantity inflation | Weighbridge net materially below invoice quantity | C4, C2 |
| F4 | Double use | The same set of inbound invoices and e-way bills appears in two processors' dossiers (only visible with a cross-processor view), plus one weighbridge ticket reused within a dossier | C5 |
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

**F4 mechanics:** PWP-10's dossier contains a copy of one of PWP-01's real inbound invoice + e-way-bill records (same invoice no., supplier GSTIN, EWB number) but with no matching weighbridge slip on PWP-10's side — so C5 (and the fact that it's unmatched) attributes the duplicate to PWP-10, while PWP-01's original, properly matched shipment stays clean. PWP-10 also carries the "one weighbridge ticket reused within a dossier" sub-case internally.

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

**Protocol:** all parameters in `params.py` and all prompts are frozen (tagged commit) before the seed-7 test set is generated. Reported numbers come from seed 7 only. Seed-42 numbers may be shown as "development set", clearly labelled.

Report all metrics honestly, including weak ones. The `/evaluation` page states that the test set is synthetic and seeded from documented issue types.
