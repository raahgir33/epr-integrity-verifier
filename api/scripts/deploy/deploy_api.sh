#!/usr/bin/env bash
# Deploys epr-api to Cloud Run. Run by the developer — never by the agent.
# Usage: api/scripts/deploy/deploy_api.sh
#
# PUSH_TOKEN (T13's live event path, POST /events/certificate-batch) is
# now required — generate one with `openssl rand -hex 32`, add it to
# api/.env, and create/update the push subscription with the SAME value
# (docs/GCP_SETUP.md §8) before relying on this endpoint. PUSH_TOKEN also
# now gates POST /admin/reset-demo (T13.8).
#
# CORS_ALLOWED_ORIGINS (T13.8) is also required — comma-separated, no
# wildcard; set it in api/.env to the deployed epr-web URL(s) plus any
# local dev origin (see api/.env.example).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="api/.env"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: $ENV_FILE not found. Create it from api/.env.example with real values first." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

# GCP_PROJECT comes from api/.env (or an already-exported shell var); only
# falls back to gcloud's own configured project if neither is set — never
# hardcoded here.
if [[ -z "${GCP_PROJECT:-}" ]]; then
  GCP_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
fi

for var in GCP_PROJECT VERTEX_LOCATION GEMINI_MODEL BQ_DATASET DOSSIER_BUCKET ARTIFACT_BUCKET PUBSUB_TOPIC PUSH_TOKEN CORS_ALLOWED_ORIGINS; do
  if [[ -z "${!var:-}" ]]; then
    echo "error: $var is not set in $ENV_FILE (and no gcloud fallback available for it)" >&2
    exit 1
  fi
done

# Agent/extract timeouts: mirror app/config.py's own defaults (see that
# file's comments for how each was derived from observed llm_calls
# latency). Set explicitly here, rather than left to the code defaults,
# so the effective config is visible in `gcloud run services describe`
# and tunable with `gcloud run services update --update-env-vars` alone.
# Keep these in sync with app/config.py if its defaults ever change.
AGENT_HYPOTHESIS_TIMEOUT_MS=120000
AGENT_CRITIC_TOOLS_TIMEOUT_MS=30000
AGENT_CRITIC_FINAL_TIMEOUT_MS=30000
AGENT_REVISION_TIMEOUT_MS=30000
EXTRACT_REQUEST_TIMEOUT_MS=120000

# Fixed for this deployment of the demo dataset (docs/BUILD_PLAN.md) —
# not a per-developer/per-environment value like the vars above, so it's
# a literal here rather than sourced from .env. Switches to "extracted"
# once the full 496-document extraction run has happened (see
# docs/PROGRESS.md's Deferred Items ledger).
DEFAULT_SEED=42
# DEFAULT_FACTS_SOURCE=truth
DEFAULT_FACTS_SOURCE=extracted

ENV_VARS="GCP_PROJECT=${GCP_PROJECT}"
ENV_VARS+=",VERTEX_LOCATION=${VERTEX_LOCATION}"
ENV_VARS+=",GEMINI_MODEL=${GEMINI_MODEL}"
ENV_VARS+=",BQ_DATASET=${BQ_DATASET}"
ENV_VARS+=",DOSSIER_BUCKET=${DOSSIER_BUCKET}"
ENV_VARS+=",ARTIFACT_BUCKET=${ARTIFACT_BUCKET}"
ENV_VARS+=",PUBSUB_TOPIC=${PUBSUB_TOPIC}"
ENV_VARS+=",PUSH_TOKEN=${PUSH_TOKEN}"
ENV_VARS+=",CORS_ALLOWED_ORIGINS=${CORS_ALLOWED_ORIGINS}"
ENV_VARS+=",DEFAULT_SEED=${DEFAULT_SEED}"
ENV_VARS+=",DEFAULT_FACTS_SOURCE=${DEFAULT_FACTS_SOURCE}"
ENV_VARS+=",AGENT_HYPOTHESIS_TIMEOUT_MS=${AGENT_HYPOTHESIS_TIMEOUT_MS}"
ENV_VARS+=",AGENT_CRITIC_TOOLS_TIMEOUT_MS=${AGENT_CRITIC_TOOLS_TIMEOUT_MS}"
ENV_VARS+=",AGENT_CRITIC_FINAL_TIMEOUT_MS=${AGENT_CRITIC_FINAL_TIMEOUT_MS}"
ENV_VARS+=",AGENT_REVISION_TIMEOUT_MS=${AGENT_REVISION_TIMEOUT_MS}"
ENV_VARS+=",EXTRACT_REQUEST_TIMEOUT_MS=${EXTRACT_REQUEST_TIMEOUT_MS}"

echo "Deploying epr-api to project $GCP_PROJECT in $VERTEX_LOCATION..."

# --max-instances=1 (T13): app/store/cache.py's cache is per-process and
# never expires on wall-clock time alone (NO_EXPIRY) — a live demo run's
# cache.invalidate()+cache.preload() only updates the ONE instance that
# served the push. With more than one instance, any other instance would
# keep serving stale pre-batch data indefinitely. Capping at 1 makes
# "exactly one process, one cache" an invariant rather than a race; the
# one-demo-run-at-a-time abuse gate (app/main.py) already assumes this
# too, so there's no concurrency given up that the feature was relying
# on anyway.
gcloud run deploy epr-api --source=api --region="$VERTEX_LOCATION" \
  --service-account="epr-api-sa@${GCP_PROJECT}.iam.gserviceaccount.com" \
  --allow-unauthenticated --timeout=600 --memory=1Gi --cpu-boost \
  --min-instances=1 --max-instances=1 \
  --set-env-vars="$ENV_VARS"

API_URL="$(gcloud run services describe epr-api --region="$VERTEX_LOCATION" --format='value(status.url)')"
if [[ -z "$API_URL" ]]; then
  echo "error: deploy succeeded but 'gcloud run services describe epr-api' returned no URL" >&2
  exit 1
fi

echo ""
echo "epr-api deployed: $API_URL"
echo "Verify with: curl ${API_URL}/health"
echo "Then deploy web with: api/scripts/deploy/deploy_web.sh"
