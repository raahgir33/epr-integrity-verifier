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

Deployment scripts live in `api/scripts/deploy/`. Run them yourself. Equivalent commands:

```bash
# API
gcloud run deploy epr-api --source=api --region=asia-south1 \
  --service-account=epr-api-sa@PROJECT_ID.iam.gserviceaccount.com \
  --allow-unauthenticated --timeout=600 --memory=1Gi \
  --set-env-vars=GCP_PROJECT=PROJECT_ID,VERTEX_LOCATION=asia-south1,GEMINI_MODEL=gemini-3.5-flash,BQ_DATASET=epr,DOSSIER_BUCKET=PROJECT_ID-epr-dossiers,ARTIFACT_BUCKET=PROJECT_ID-epr-artifacts,PUBSUB_TOPIC=certificate-batches,PUSH_TOKEN=CHOOSE_A_LONG_RANDOM_STRING

# Web (after the API URL is known)
gcloud run deploy epr-web --source=web --region=asia-south1 \
  --service-account=epr-web-sa@PROJECT_ID.iam.gserviceaccount.com \
  --allow-unauthenticated --memory=512Mi \
  --set-env-vars=API_BASE_URL=https://EPR_API_URL

# Push subscription (after the API URL is known)
gcloud pubsub subscriptions create certificate-batches-push \
  --topic=certificate-batches \
  --push-endpoint="https://EPR_API_URL/events/certificate-batch?token=SAME_PUSH_TOKEN" \
  --ack-deadline=600
```

From 9 October until results: add `--min-instances=1` to both services (`gcloud run services update epr-api --min-instances=1`, same for `epr-web`).

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
