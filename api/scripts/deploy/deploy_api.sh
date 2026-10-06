#!/usr/bin/env bash
# Deploys epr-api to Cloud Run. Run by the developer — never by the agent.
# Usage: api/scripts/deploy/deploy_api.sh
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

for var in GCP_PROJECT VERTEX_LOCATION GEMINI_MODEL BQ_DATASET DOSSIER_BUCKET ARTIFACT_BUCKET PUBSUB_TOPIC PUSH_TOKEN; do
  if [[ -z "${!var:-}" ]]; then
    echo "error: $var is not set in $ENV_FILE" >&2
    exit 1
  fi
done

echo "Deploying epr-api to project $GCP_PROJECT in $VERTEX_LOCATION..."

gcloud run deploy epr-api --source=api --region="$VERTEX_LOCATION" \
  --service-account="epr-api-sa@${GCP_PROJECT}.iam.gserviceaccount.com" \
  --allow-unauthenticated --timeout=600 --memory=1Gi \
  --set-env-vars="GCP_PROJECT=${GCP_PROJECT},VERTEX_LOCATION=${VERTEX_LOCATION},GEMINI_MODEL=${GEMINI_MODEL},BQ_DATASET=${BQ_DATASET},DOSSIER_BUCKET=${DOSSIER_BUCKET},ARTIFACT_BUCKET=${ARTIFACT_BUCKET},PUBSUB_TOPIC=${PUBSUB_TOPIC},PUSH_TOKEN=${PUSH_TOKEN}"

API_URL="$(gcloud run services describe epr-api --region="$VERTEX_LOCATION" --format='value(status.url)')"
echo "$API_URL" > "$REPO_ROOT/api/scripts/deploy/.epr-api-url"

echo ""
echo "epr-api deployed: $API_URL"
echo "Verify with: curl ${API_URL}/health"
echo "Then deploy web with: api/scripts/deploy/deploy_web.sh"
