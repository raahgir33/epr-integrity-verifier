# Google Cloud Setup

All steps here are run by the developer. The application code never creates or modifies cloud resources.

Replace `PROJECT_ID` with your project ID throughout. Region for everything: `asia-south1`.

## 0. Before you start (do these today; some take time)

- [ ] Project created and linked to billing.
- [ ] **Budget alert** set (Billing → Budgets & alerts), e.g. ₹5,000 with alerts at 50%, 90%, 100%.
- [ ] **Earth Engine registration** started at https://code.earthengine.google.com/register for this Cloud project (choose the noncommercial / research option if eligible). This can take time; start it first.

```bash
gcloud config set project PROJECT_ID
gcloud config set run/region asia-south1
```

## 1. Enable APIs

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  bigquery.googleapis.com \
  storage.googleapis.com \
  pubsub.googleapis.com \
  earthengine.googleapis.com \
  iam.googleapis.com
```

## 2. Storage buckets

```bash
gcloud storage buckets create gs://PROJECT_ID-epr-dossiers  --location=asia-south1 --uniform-bucket-level-access
gcloud storage buckets create gs://PROJECT_ID-epr-artifacts --location=asia-south1 --uniform-bucket-level-access
```

## 3. BigQuery dataset

```bash
bq --location=asia-south1 mk --dataset PROJECT_ID:epr
```

Tables are created by `api/scripts/deploy/create_tables.py` (run it yourself once the code exists).

## 4. Pub/Sub topic

```bash
gcloud pubsub topics create certificate-batches
```

The push subscription is created in step 8, after the API is deployed and has a URL.

## 5. Service accounts and roles

```bash
gcloud iam service-accounts create epr-api-sa --display-name="EPR API"
gcloud iam service-accounts create epr-web-sa --display-name="EPR Web"

SA=epr-api-sa@PROJECT_ID.iam.gserviceaccount.com
for ROLE in roles/aiplatform.user roles/bigquery.dataEditor roles/bigquery.jobUser \
            roles/pubsub.publisher roles/earthengine.viewer roles/serviceusage.serviceUsageConsumer; do
  gcloud projects add-iam-policy-binding PROJECT_ID --member="serviceAccount:$SA" --role="$ROLE"
done

gcloud storage buckets add-iam-policy-binding gs://PROJECT_ID-epr-dossiers  --member="serviceAccount:$SA" --role=roles/storage.objectAdmin
gcloud storage buckets add-iam-policy-binding gs://PROJECT_ID-epr-artifacts --member="serviceAccount:$SA" --role=roles/storage.objectAdmin
```

`epr-web-sa` needs no roles: the web app only calls the public API.

## 6. Local credentials

```bash
gcloud auth login
gcloud auth application-default login
gcloud auth application-default set-quota-project PROJECT_ID
```

If Earth Engine initialisation fails locally after this, run `earthengine authenticate` (from the `earthengine-api` package) and retry.

## 7. Smoke tests (gate before any feature work)

Run from `api/` once the scripts exist:

```bash
uv run python scripts/smoke/smoke_gemini.py   # model gemini-3.5-flash in asia-south1; structured output on a sample PDF
uv run python scripts/smoke/smoke_bq.py       # query in asia-south1
uv run python scripts/smoke/smoke_gcs.py      # upload, read back, delete a test object
uv run python scripts/smoke/smoke_pubsub.py   # publish one message
uv run python scripts/smoke/smoke_ee.py       # Open Buildings count near a test coordinate
```

All five must pass. If Gemini fails on region or model, stop and record the exact error in `docs/PROGRESS.md`.

## 8. Deploy

Deployment scripts live in `api/scripts/deploy/`. Run them yourself:

```bash
api/scripts/deploy/deploy_api.sh   # epr-api — prints its URL at the end
api/scripts/deploy/deploy_web.sh   # epr-web — reads epr-api's URL automatically
```

Equivalent commands, for reference (the scripts also fill in every agent/extract timeout setting from `app/config.py`'s defaults — omitted below for brevity; see `deploy_api.sh`):

```bash
# API — PUSH_TOKEN is required (T13's live event path). Generate with
# `openssl rand -hex 32` and use the SAME value in the push subscription
# below. --max-instances=1 (T13): app/store/cache.py's cache is per-
# process and never expires on its own (NO_EXPIRY) — a live demo run's
# cache.invalidate()+preload() only updates the instance that served the
# push, so more than one instance risks another one serving stale data
# indefinitely.
gcloud run deploy epr-api --source=api --region=asia-south1 \
  --service-account=epr-api-sa@PROJECT_ID.iam.gserviceaccount.com \
  --allow-unauthenticated --timeout=600 --memory=1Gi --cpu-boost \
  --min-instances=1 --max-instances=1 \
  --set-env-vars=GCP_PROJECT=PROJECT_ID,VERTEX_LOCATION=asia-south1,GEMINI_MODEL=gemini-3.5-flash,BQ_DATASET=epr,DOSSIER_BUCKET=PROJECT_ID-epr-dossiers,ARTIFACT_BUCKET=PROJECT_ID-epr-artifacts,PUBSUB_TOPIC=certificate-batches,PUSH_TOKEN=YOUR_PUSH_TOKEN,DEFAULT_SEED=42,DEFAULT_FACTS_SOURCE=extracted

# Web — API_BASE_URL is read live from `gcloud run services describe epr-api`,
# never hardcoded or cached, so it always points at whatever epr-api
# currently is
EPR_API_URL="$(gcloud run services describe epr-api --region=asia-south1 --format='value(status.url)')"
gcloud run deploy epr-web --source=web --region=asia-south1 \
  --service-account=epr-web-sa@PROJECT_ID.iam.gserviceaccount.com \
  --allow-unauthenticated --memory=512Mi --cpu-boost \
  --set-env-vars="API_BASE_URL=${EPR_API_URL}"

# Push subscription (T13 — after the API URL is known and PUSH_TOKEN has
# been set on epr-api's env vars). ack-deadline=600 covers even the
# agent loop's worst-case processor-level retry (two full 300s attempts).
gcloud pubsub subscriptions create certificate-batches-push \
  --topic=certificate-batches \
  --push-endpoint="${EPR_API_URL}/events/certificate-batch?token=SAME_PUSH_TOKEN" \
  --ack-deadline=600
```

Both services run with `--min-instances=1` from 9 October until results are announced (`gcloud run services update epr-web --min-instances=1`; `epr-api` already has it, above). `epr-api` additionally keeps `--max-instances=1` permanently, for cache coherence — never relax this unless app/store/cache.py's per-process cache is also redesigned for multiple instances.

## 8a. Post-deploy verification

Run these after every `deploy_api.sh`/`deploy_web.sh`. `API_URL` is the URL `deploy_api.sh` printed.

**Health and consistency.** `consistency_ok` reflects `app/store/cache.check_consistency()` (docs/ARCHITECTURE.md §7) — it should be `true`, never `false`; `null` means the request raced startup and should clear on a retry a few seconds later.

```bash
curl -s "${API_URL}/health" | python3 -m json.tool
```

**First-request latency.** `app/main.py`'s `lifespan` blocks on `preload()` before the app reports ready, so even the *first* request after a cold start should already be warm — this is the regression to watch for (see `app/store/cache.py`'s A2 fix: a short TTL was previously undermining "preload once, stay warm").

```bash
# cold (first request after a fresh revision/instance)
curl -s -o /dev/null -w "cold: %{time_total}s (HTTP %{http_code})\n" "${API_URL}/processors/PWP-08"
# warm (immediately after)
curl -s -o /dev/null -w "warm: %{time_total}s (HTTP %{http_code})\n" "${API_URL}/processors/PWP-08"
```

Both should be well under 1s. If "cold" is many seconds slower than "warm", `preload()` is running later than startup (check the startup log query below) rather than being blocked on as intended.

**Startup log.** Confirms `preload()` + `check_consistency()` actually ran at boot, and how long they took (`app/main.py` logs this once, after both finish).

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="epr-api" AND textPayload:"startup complete"' \
  --project=PROJECT_ID --freshness=1h --limit=5 --format='value(timestamp, textPayload)'
```

**Out-of-memory check.** `--memory=1Gi` is a guess, not a measured figure — watch for Cloud Run's own OOM log line, especially right after a cold start (preload loads all of seed 42's tables and site thumbnails into memory at once) or during an agent run.

```bash
gcloud logging read \
  'resource.type="cloud_run_revision" AND resource.labels.service_name="epr-api" AND severity>=ERROR AND textPayload:"Memory limit"' \
  --project=PROJECT_ID --freshness=1d --limit=20 --format='value(timestamp, textPayload)'
```

An empty result is good. If it's not empty, raise `--memory` on `epr-api` (`gcloud run services update epr-api --memory=2Gi`) rather than investigating further — this dataset's size is fixed and known, not a leak to chase.

## 9. Troubleshooting source deploys

Cloud Build uses the Compute Engine default service account (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`) to build source deploys. If `gcloud run deploy --source` fails with a permission error, grant it the Cloud Run Builder role:

```bash
PROJECT_NUMBER=$(gcloud projects describe PROJECT_ID --format='value(projectNumber)')
gcloud projects add-iam-policy-binding PROJECT_ID \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role=roles/run.builder
```

Your own account needs Cloud Run Source Developer, Service Usage Consumer, and Service Account User on the runtime service accounts. As project owner you already have these.

## 10. Resource register (fill in as you create them)

| Resource | Name | Created on | Notes |
|---|---|---|---|
| Project | | | |
| Dossier bucket | PROJECT_ID-epr-dossiers | | |
| Artifact bucket | PROJECT_ID-epr-artifacts | | |
| BigQuery dataset | epr | | asia-south1 |
| Pub/Sub topic | certificate-batches | | |
| Push subscription | certificate-batches-push | | |
| API service | epr-api | | URL: |
| Web service | epr-web | | URL: |
| Earth Engine registration | | | status: |
