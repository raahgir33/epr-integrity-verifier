# EPR Integrity Verifier

An independent verifier for India's plastic packaging EPR (Extended Producer Responsibility)
certificates. It ingests a Plastic Waste Processor's documents, reconstructs the material
flow, tests it against physical and documentary constraints, and reports how many certified
tonnes are verifiable, with evidence for every finding.

All data in this repository is synthetic and clearly watermarked; no real companies, recyclers or brands are represented.

## Repository layout

- `api/` — Python 3.12, FastAPI, Cloud Run service `epr-api`. Extraction, checks, agents.
- `web/` — Next.js (App Router, TypeScript), Cloud Run service `epr-web`. Reporting UI.
- `data/synthetic/` — generated dossiers and ground truth (reproducible from a seed).
- `assets/fonts/` — fonts used to render Hindi documents.
- `docs/` — architecture, data spec and GCP setup notes.

## Running locally

### API

```bash
cd api
uv sync
uv run uvicorn app.main:app --reload --port 8080
```

`GET http://localhost:8080/health` returns status, model and region.

### Web

```bash
cd web
npm install
API_BASE_URL=http://localhost:8080 npm run dev
```

Open `http://localhost:3000` — the home page shows the API's health.

## Tests and lint

```bash
cd api && uv run pytest -q && uv run ruff check . && uv run ruff format --check .
cd web && npm run lint && npx tsc --noEmit && npm run build
```
