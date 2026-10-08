# Architecture

## 1. Purpose

Independently verify plastic packaging EPR certificates issued in India. For each Plastic Waste Processor (PWP), the system answers one question with evidence: **how many of the tonnes it certified can be traced to plausible, consistent, physically possible material flows?**

Output units are environmental: certified tonnes, verifiable tonnes, unverifiable tonnes.

## 2. System overview

```
                    ┌────────────────────────── Google Cloud (asia-south1) ──────────────────────────┐
                    │                                                                                 │
 Synthetic          │  Cloud Storage                BigQuery (dataset: epr)                           │
 dossiers  ───────▶ │  epr-dossiers bucket  ──────▶ documents, extracted_facts, shipments,            │
 (PDF, PNG)         │                               outputs, energy_monthly, certificates,            │
                    │                               check_results, site_assessments, agent_runs,      │
                    │                               assessments, alerts, llm_calls, eval_results      │
                    │        │                                  ▲            ▲                        │
                    │        ▼                                  │            │                        │
                    │  ┌──────────────── epr-api (Cloud Run, FastAPI) ────────────────┐               │
                    │  │ ingest/extract ──▶ Gemini on Vertex AI (gemini-3.5-flash)     │               │
                    │  │ ingest/normalize                                              │               │
                    │  │ checks/ C1–C7 (deterministic)                                 │               │
                    │  │ geo/site C8 ──────▶ Earth Engine (Open Buildings, Sentinel-2) │               │
                    │  │ agents/ Hypothesis ⇄ Critic(tools) ▶ Scorer ──▶ Gemini        │               │
                    │  │ events/ push handler ◀── Pub/Sub topic: certificate-batches   │               │
                    │  └───────────────────────────────▲───────────────────────────────┘               │
                    │                                  │ HTTPS (server-side fetch)                     │
                    │  ┌──────────────── epr-web (Cloud Run, Next.js) ────────────────┐               │
                    │  │ Overview · Processor dossier · Brand portfolio · Evaluation · Method          │
                    │  └────────────────────────────────────────────────────────────────┘             │
                    └─────────────────────────────────────────────────────────────────────────────────┘
```

## 3. Data flow

### 3.1 Batch precompute (run before the demo, idempotent)

1. **Generate** seeded synthetic dossiers, `ground_truth.json`, `suppliers.json` and `demo_batches.json` (`scripts/generate_dossiers.py`; seed 42 for development, seed 7 held out for the reported test).
2. **Load** documents to Cloud Storage; register processors, suppliers, documents, certificates and brands in BigQuery (`scripts/load_dossiers.py`).
3. **Extract** each document with Gemini into a typed schema with per-field confidence and source page (`ingest/extract.py` → `extracted_facts`). Values are captured exactly as printed; `ingest/units.py` parses them. Results are cached by document hash, so re-runs skip already-extracted documents.
4. **Normalise** facts into analysis tables using the matching rules in `docs/DATA_SPEC.md` §4 (`ingest/normalize.py` → `shipments`, `outputs`, `energy_monthly`). Unmatched records are kept and flagged. With `--facts-source truth`, these tables are built from ground truth instead, so steps 5–8 can be developed while extraction is still being built.
5. **Check** each processor with deterministic checks C1–C7 (`checks/runner.py` → `check_results`).
6. **Site** check C8 with Earth Engine; store results and a thumbnail (`geo/site.py` → `site_assessments`, Cloud Storage).
7. **Reason** with the agent loop (`agents/orchestrator.py` → `agent_runs`, `assessments`).
8. **Evaluate** against ground truth (`scripts/run_eval.py` → `eval_results`).

### 3.2 Live event path (demo moment)

1. User clicks **Simulate new certificate batch** for a processor in the web app.
2. `POST /demo/certificate-batch` takes the scripted batch for that processor from `demo_batches`, creates a run record (`status = queued`), returns its `run_id`, and publishes a message to Pub/Sub topic `certificate-batches`.
3. The push subscription calls `POST /events/certificate-batch?token=…` on `epr-api`.
4. The handler, synchronously within the request and idempotent on message ID, adds the batch to the certificate ledger, re-runs checks and the agent loop for that processor (no re-extraction is needed), writes a new assessment, and writes an alert if unverifiable tonnes increased. It updates the run status at each stage (`checking`, `reasoning`, `done` or `failed`) and only then returns 2xx.
5. The web app polls `GET /runs/{run_id}` every 3 seconds to show progress, then `GET /alerts`, and shows the alert with a link to the evidence.
6. A reset endpoint is not exposed publicly; `scripts/reset_demo.py` (developer-run) removes demo batches so the demo can be repeated.

## 4. The agent loop

The loop exists to do what deterministic checks cannot: read meaning in documents, connect evidence across the dossier, and challenge a first conclusion.

```
                ┌─────────────────────────────────────────────┐
 Processor ───▶ │ Context pack: profile, consent terms,        │
 facts +        │ monthly material flow, check results with    │
 check results  │ evidence IDs, site result                    │
                └───────────────┬─────────────────────────────┘
                                ▼
                     ┌─────────────────────┐
                     │ 1. Hypothesis agent │  For each certificate batch: supported /
                     │    (Gemini)         │  partly supported / unsupported, with
                     └─────────┬───────────┘  cited evidence IDs.
                               ▼
                     ┌─────────────────────┐   Tools (function calling):
                     │ 2. Critic agent     │   run_check, get_document_facts,
                     │    (Gemini + tools) │   get_shipments, get_site_assessment,
                     └─────────┬───────────┘   read_document (multimodal, by gs:// URI)
                               ▼               Produces objections, each with evidence.
                     ┌─────────────────────┐
                     │ 3. Hypothesis       │   Accepts or rebuts each objection.
                     │    revision (once)  │
                     └─────────┬───────────┘
                               ▼
                     ┌─────────────────────┐   Deterministic: converts confirmed findings
                     │ 4. Scorer           │   into verifiable / unverifiable tonnes and a
                     │    (Python + Gemini │   risk band. Gemini writes the plain-language
                     │     for narrative)  │   summary from the computed numbers only.
                     └─────────────────────┘
```

**Context pack (built in code, compact):** processor profile and consent terms; monthly table of certified, inbound and capacity tonnes; every check result with evidence IDs; site result; and a **dossier digest**, meaning every distinct inbound item description with its HSN code and the shipment IDs it appears on, every non-empty weighbridge remark, and every unmatched record. The digest is what lets the agents notice semantic contradictions without re-reading every file.

**Two-phase Critic:** phase 1 is a function-calling loop (tools listed above); phase 2 is a separate call without tools that returns the objections in a structured schema. Tool results are returned as short summaries (at most ~2 KB each), never whole tables.

**Rules enforced in code, not prompts:**
- A finding without at least one valid evidence ID is discarded.
- A finding that should reduce verifiable tonnes must cite the affected shipment IDs; the Scorer deducts exactly those shipments' tonnes and nothing else.
- A failed hard deterministic check cannot be overruled by an agent.
- Agents may add findings that checks cannot see (semantic contradictions), but each must cite document evidence and is labelled "agent finding".
- Maximum one revision round; maximum 8 tool calls per Critic run; per-run timeout 300 s (raised from 180 s, 2026-10-08 — docs/PROGRESS.md: an intermittent ~120s-class backend stall on agent_critic_tools, retried, needed more than 180 s of total wall-clock even after the retry succeeded quickly).
- Every step is stored in `agent_runs` and shown in the UI as the reasoning trail.

## 5. Deterministic checks

Defined in `docs/DATA_SPEC.md` §4 with parameters in `api/app/checks/params.py`.

| ID | Check | Type |
|---|---|---|
| C1 | FY-to-date certified tonnes within consented capacity | Hard |
| C2a | FY-to-date certified tonnes within verified inbound waste | Hard |
| C2b | Recycled output sold within processed tonnes × maximum yield (recyclers only) | Soft |
| C3 | Transport plausibility (implied speed, e-way bill validity) | Hard |
| C4 | Cross-document consistency (quantities, GSTIN, vehicle) | Hard |
| C5 | Duplicate use of an e-way bill, ticket or invoice, within or **across** processors | Hard |
| C6 | Activity within consent validity and permitted category | Hard |
| C7 | Electricity consumption plausible for processed tonnes (recyclers only) | Soft |
| C8 | Site plausibility from satellite-derived building footprint | Soft |

Verifiable tonnes and the risk band are computed deterministically from these results and confirmed agent findings; see `docs/DATA_SPEC.md` §4a.

## 6. Services and why each is used

| Service | Role | Why it earns its place |
|---|---|---|
| Gemini on Vertex AI (`gemini-3.5-flash`, `asia-south1`) | Extraction, translation, Hypothesis and Critic agents, narratives | Core reasoning |
| BigQuery | All structured data, checks across processors, evaluation | Cross-processor analysis ("certified vs capacity across all PWPs") |
| Cloud Storage | Dossier files, Earth Engine thumbnails | Document and imagery store |
| Earth Engine | Open Buildings footprints and Sentinel-2 imagery at registered sites | Physical plausibility of claimed capacity |
| Pub/Sub | New certificate batch events | Event-driven re-verification and alerts |
| Cloud Run | `epr-api` and `epr-web` | Mandatory deployment target |
| Cloud Build, Artifact Registry | Container builds for Cloud Run source deploys | Deployment |

Not used: Vertex AI predictive model training (a model trained only on synthetic data would not be credible).

## 7. API surface (`epr-api`)

The API serves exactly one configured `(seed, facts_source)` (`app/config.py`'s `default_seed`/`default_facts_source` — `42`/`"truth"` until the full extraction run, then `"extracted"`). Every response's `meta` field echoes both; a response never mixes the two.

| Method | Path | Returns |
|---|---|---|
| GET | `/health` | Status, model, region, `consistency_ok` (see below) |
| GET | `/processors` | List with both assessment stages (`checks_only`, `full`) side by side, risk band, `agent_status` |
| GET | `/processors/{id}` | Profile, monthly flow, check results (each with its `params.py` source/ASSUMPTION label), both assessment stages, agent findings |
| GET | `/processors/{id}/documents` | Document list with types and extraction status (`"ok"` / `"failed"` / `"not_extracted"`) |
| GET | `/documents/{doc_id}/file` | Streams the file from Cloud Storage; `doc_id` validated against `documents` for the configured seed first |
| GET | `/documents/{doc_id}/facts` | Extracted fields with confidence and page, independent of `facts_source` |
| GET | `/processors/{id}/reasoning` | Agent run trail (Hypothesis → Critic tool calls → verdicts → revision), plus the same agent findings as `/processors/{id}` |
| GET | `/processors/{id}/site` | Site assessment, thumbnail reference, attribution strings, synthetic-data disclaimer |
| GET | `/site-images/{id}` | Streams the thumbnail; validated against `site_assessments` first |
| GET | `/portfolio/{brand_id}` | A brand's certificates across processors and an apportioned verifiable share (see note below) |
| GET | `/evaluation` | Explicit `available: false` stub — `eval_results` doesn't exist until T14 |
| GET | `/alerts` | Explicit empty list — `alerts` doesn't exist until T13 |
| POST | `/demo/certificate-batch` | Creates a run, publishes the scripted batch event, returns `run_id` (T13) |
| GET | `/runs/{run_id}` | Run status: queued, checking, reasoning, done, failed (T13) |
| POST | `/events/certificate-batch` | Pub/Sub push endpoint (token-protected) (T13) |

All GET endpoints serve from the in-process read cache (`store/cache.py`, TTL 60 s). The configured `(seed, facts_source)`'s tables are preloaded into the cache once at startup (every table is small — 10 processors, ~150 shipments, ~700 documents — so this costs one request's worth of BigQuery queries total, not per request); a lazy `get_or_load` with the same TTL serves anything not preloaded (e.g. one document's extracted facts). `invalidate()` exists for T13's live event path to call after writing a new assessment — not used by anything in T11.

**Two assessment stages.** `/processors` and `/processors/{id}` both return `checks_only` and `full` (nullable — `null` until the agent stage has run for that processor) side by side, plus `agent_status` (`"ok"` / `"timeout"` / `"error"` / `null`), so the UI can show the agent's own contribution against the deterministic baseline.

**Agent findings aren't stored per-finding in BigQuery — they're reconstructed.** Only each finding's *aggregate* scoring effect is persisted (`assessments`'s tonnage figures, the three synthetic `AGENT_SYSTEMIC_FINDING`/`AGENT_NO_OWN_EVIDENCE_FINDING`/`AGENT_DISPUTED_FINDING` check results) — the per-finding classification (`deductible` / `systemic` / `no_own_evidence` / `concurs_with_check` / `review_flag` / `withdrawn`), origin (`hypothesis` / `critic`), and verdict/revision detail live only in the `agent_runs` trail's raw structured output while the pipeline runs. `app/agents/orchestrator.py`'s `reconstruct_agent_findings` rebuilds the full finding list from a stored trail plus the processor's *current* `check_results`/`shipments` — the same classification logic `scripts/probe_agent_thinking.py --rescore` already runs offline, now also driving the read path, with no new Gemini call and no new BigQuery table.

**Consistency guard.** Because agent findings are reconstructed rather than stored (above), `app/store/cache.py`'s `check_consistency` cross-checks that reconstruction against reality once at startup (after preload): for every processor with a stored `stage="full"` assessment, it rebuilds the finding list and recomputes `score_processor` with the resulting deduction set, and compares the recomputed `verifiable_t` to the stored one. `GET /health`'s `consistency_ok` reflects the result (`null` before the first check has run); a mismatch is also logged as an error, since nothing else would surface a drift between the reconstruction logic and what the pipeline actually scored.

**Portfolio apportionment is derived, not traced.** `total_verifiable_t` is each certificate's `quantity_t` scaled by its own processor's `verifiable_t / certified_t` ratio (preferring the `full` stage, falling back to `checks_only`) and summed — scoring never happens below the processor/FY-to-date level anywhere upstream, so this is an apportionment, not a per-certificate traced figure.

OpenAPI schema: `uv run python scripts/export_openapi.py` writes `api/openapi.json`, which T12 generates TypeScript types from.

## 7a. Data write policy

- BigQuery writes use load jobs or DML only, never streaming inserts.
- Writes are batched: one load per table per pipeline stage or per processor run.
- Idempotent re-runs: delete by `run_id` / `processor_id` with DML, then load.

## 8. Web app (`epr-web`)

| Route | Purpose |
|---|---|
| `/` | Overview: total certified vs verifiable tonnes across processors; processor table; live alerts |
| `/processors/[id]` | Dossier: headline numbers, monthly material-flow chart, findings with evidence, reasoning trail, site panel, documents |
| `/portfolio` | A brand's view: certificates held and the share that is verifiable |
| `/evaluation` | Accuracy against seeded ground truth; checks-only vs full system |
| `/method` | How checks work, sources, assumptions, dataset attribution (Open Buildings CC-BY-4.0; "Contains modified Copernicus Sentinel data"), synthetic-data notice |

Documents open through a Next.js route handler (`/files/[docId]`) that proxies the API, so they are same-origin. The site panel draws Open Buildings polygons as SVG over the upsampled Sentinel-2 thumbnail (~1 km box, 512 px).

## 9. Deployment

| Setting | `epr-api` | `epr-web` |
|---|---|---|
| Region | asia-south1 | asia-south1 |
| Service account | `epr-api-sa` | `epr-web-sa` |
| Min instances | 1 (from 9 Oct) | 1 (from 9 Oct) |
| CPU throttling | Default (all work is synchronous within requests) | Default |
| Timeout | 600 s | 60 s |
| Ingress / auth | Public; push endpoint requires token | Public |
| Key env | `GCP_PROJECT`, `VERTEX_LOCATION`, `GEMINI_MODEL`, `BQ_DATASET`, `DOSSIER_BUCKET`, `ARTIFACT_BUCKET`, `PUBSUB_TOPIC`, `PUSH_TOKEN` | `API_BASE_URL` |
| Concurrency | Default (80); a live run holds one request for 1–3 minutes | Default |

## 10. Security and data notes

- All data is synthetic and watermarked; entities are fictional.
- No personal data is processed.
- The push endpoint validates a shared token; write endpoints are limited to the demo batch trigger, rate-limited to one request per 10 seconds per processor.
- The push token appears in Cloud Run request logs because it is a query parameter. Acceptable for a demo with synthetic data; Pub/Sub OIDC push authentication is the production upgrade.
- Coordinates are shown rounded to 2 decimal places and no addresses are displayed, so no real business at a map location is implied.
