#!/usr/bin/env bash
# Deploys epr-web to Cloud Run. Run by the developer — never by the agent.
# Usage: api/scripts/deploy/deploy_web.sh [api-url]
#   api-url is optional if deploy_api.sh already ran on this machine —
#   it falls back to the URL that script recorded.
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

for var in GCP_PROJECT VERTEX_LOCATION; do
  if [[ -z "${!var:-}" ]]; then
    echo "error: $var is not set in $ENV_FILE" >&2
    exit 1
  fi
done

API_URL="${1:-}"
URL_FILE="$REPO_ROOT/api/scripts/deploy/.epr-api-url"
if [[ -z "$API_URL" && -f "$URL_FILE" ]]; then
  API_URL="$(cat "$URL_FILE")"
fi

if [[ -z "$API_URL" ]]; then
  echo "error: no API URL given and $URL_FILE does not exist." >&2
  echo "Run deploy_api.sh first, or pass the URL explicitly:" >&2
  echo "  api/scripts/deploy/deploy_web.sh https://epr-api-....run.app" >&2
  exit 1
fi

echo "Deploying epr-web to project $GCP_PROJECT in $VERTEX_LOCATION, API_BASE_URL=$API_URL ..."

gcloud run deploy epr-web --source=web --region="$VERTEX_LOCATION" \
  --service-account="epr-web-sa@${GCP_PROJECT}.iam.gserviceaccount.com" \
  --allow-unauthenticated --memory=512Mi \
  --set-env-vars="API_BASE_URL=${API_URL}"

WEB_URL="$(gcloud run services describe epr-web --region="$VERTEX_LOCATION" --format='value(status.url)')"

echo ""
echo "epr-web deployed: $WEB_URL"
echo "Verify by opening it in a browser — it should show the live API health."
