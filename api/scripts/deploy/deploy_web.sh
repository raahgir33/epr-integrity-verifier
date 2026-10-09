#!/usr/bin/env bash
# Deploys epr-web to Cloud Run. Run by the developer — never by the agent.
# Usage: api/scripts/deploy/deploy_web.sh
#   Requires epr-api to already be deployed — its URL is read live from
#   `gcloud run services describe epr-api`, never cached or hardcoded, so
#   epr-web always points at whatever epr-api currently is.
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

if [[ -z "${GCP_PROJECT:-}" ]]; then
  GCP_PROJECT="$(gcloud config get-value project 2>/dev/null || true)"
fi

for var in GCP_PROJECT VERTEX_LOCATION; do
  if [[ -z "${!var:-}" ]]; then
    echo "error: $var is not set in $ENV_FILE (and no gcloud fallback available for it)" >&2
    exit 1
  fi
done

API_URL="$(gcloud run services describe epr-api --region="$VERTEX_LOCATION" --format='value(status.url)' 2>/dev/null || true)"
if [[ -z "$API_URL" ]]; then
  echo "error: could not read epr-api's URL from 'gcloud run services describe epr-api'." >&2
  echo "Deploy epr-api first: api/scripts/deploy/deploy_api.sh" >&2
  exit 1
fi

echo "Deploying epr-web to project $GCP_PROJECT in $VERTEX_LOCATION, API_BASE_URL=$API_URL ..."

gcloud run deploy epr-web --source=web --region="$VERTEX_LOCATION" \
  --service-account="epr-web-sa@${GCP_PROJECT}.iam.gserviceaccount.com" \
  --allow-unauthenticated --memory=512Mi --cpu-boost \
  --min-instances=1 --max-instances=3 \
  --set-env-vars="API_BASE_URL=${API_URL}"

WEB_URL="$(gcloud run services describe epr-web --region="$VERTEX_LOCATION" --format='value(status.url)')"
if [[ -z "$WEB_URL" ]]; then
  echo "error: deploy succeeded but 'gcloud run services describe epr-web' returned no URL" >&2
  exit 1
fi

echo ""
echo "epr-web deployed: $WEB_URL"
echo "Verify by opening it in a browser — it should show the live API health."
