#!/usr/bin/env bash
#
# One-command Cloud Shell deployment for the VLegal AI API:
#   1. securely configure/keep Secret Manager values;
#   2. deploy the repository source with Google Buildpacks;
#   3. bind secrets and update only the intended non-secret environment values;
#   4. verify Cloud Run health.
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-}"
REGION="${GCP_REGION:-asia-southeast1}"
SERVICE="${GCP_API_SERVICE:-vlegal-api}"
FRONTEND_URL="${VLEGAL_FRONTEND_URL:-}"
NEO4J_URI="${NEO4J_URI:-}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_DATABASE="${NEO4J_DATABASE:-neo4j}"
RUNTIME_SERVICE_ACCOUNT="${GCP_RUN_SERVICE_ACCOUNT:-}"
GEMINI_MODEL="${GEMINI_MODEL:-gemini-2.5-flash}"
EMBEDDING_LOCATION="${GCP_EMBEDDING_LOCATION:-asia-southeast1}"
CONFIGURE_SECRETS=true

usage() {
  cat <<'EOF'
Usage:
  ./scripts/gcp/deploy-api-buildpacks.sh [options]

Required:
  --project PROJECT_ID
  --frontend-url HTTPS_URL
  --neo4j-uri NEO4J_URI

Options:
  --region REGION                         (default: asia-southeast1)
  --service SERVICE_NAME                  (default: vlegal-api)
  --neo4j-user USER                       (default: neo4j)
  --neo4j-database DATABASE               (default: neo4j)
  --runtime-service-account EMAIL         (default: current service identity)
  --gemini-model MODEL                    (default: gemini-2.5-flash)
  --embedding-location REGION             (default: asia-southeast1)
  --skip-secret-setup                     reuse enabled Secret Manager versions
  -h, --help

The first run prompts for secrets with input hidden. Future runs can press Enter
to keep each version or use --skip-secret-setup.
EOF
}

while (($#)); do
  case "$1" in
    --project)
      PROJECT_ID="${2:?Missing value for --project}"
      shift 2
      ;;
    --region)
      REGION="${2:?Missing value for --region}"
      shift 2
      ;;
    --service)
      SERVICE="${2:?Missing value for --service}"
      shift 2
      ;;
    --frontend-url)
      FRONTEND_URL="${2:?Missing value for --frontend-url}"
      shift 2
      ;;
    --neo4j-uri)
      NEO4J_URI="${2:?Missing value for --neo4j-uri}"
      shift 2
      ;;
    --neo4j-user)
      NEO4J_USER="${2:?Missing value for --neo4j-user}"
      shift 2
      ;;
    --neo4j-database)
      NEO4J_DATABASE="${2:?Missing value for --neo4j-database}"
      shift 2
      ;;
    --runtime-service-account)
      RUNTIME_SERVICE_ACCOUNT="${2:?Missing value for --runtime-service-account}"
      shift 2
      ;;
    --gemini-model)
      GEMINI_MODEL="${2:?Missing value for --gemini-model}"
      shift 2
      ;;
    --embedding-location)
      EMBEDDING_LOCATION="${2:?Missing value for --embedding-location}"
      shift 2
      ;;
    --skip-secret-setup)
      CONFIGURE_SECRETS=false
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

require_command gcloud
require_command git
require_command curl
require_command python3

if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "Set --project or GOOGLE_CLOUD_PROJECT." >&2
  exit 1
fi
if [[ -z "$FRONTEND_URL" ]]; then
  echo "--frontend-url or VLEGAL_FRONTEND_URL is required." >&2
  exit 1
fi
if [[ "$FRONTEND_URL" != https://* ]]; then
  echo "Production frontend URL must start with https://." >&2
  exit 1
fi
FRONTEND_URL="${FRONTEND_URL%/}"
if [[ -z "$NEO4J_URI" ]]; then
  echo "--neo4j-uri or NEO4J_URI is required." >&2
  exit 1
fi
if [[ ! -f "$REPO_ROOT/Procfile" || ! -f "$REPO_ROOT/.python-version" ]]; then
  echo "Procfile and .python-version are required at the repository root." >&2
  exit 1
fi
if ! grep -Fqx \
  'web: python -m uvicorn app.main:app --host 0.0.0.0 --port $PORT' \
  "$REPO_ROOT/Procfile"; then
  echo "Procfile does not contain the expected Buildpacks entrypoint." >&2
  exit 1
fi

gcloud auth print-access-token >/dev/null

if [[ -z "$RUNTIME_SERVICE_ACCOUNT" ]]; then
  RUNTIME_SERVICE_ACCOUNT="$(
    gcloud run services describe "$SERVICE" \
      --project="$PROJECT_ID" \
      --region="$REGION" \
      --format='value(spec.template.spec.serviceAccountName)' \
      2>/dev/null || true
  )"
fi
if [[ -z "$RUNTIME_SERVICE_ACCOUNT" ]]; then
  project_number="$(
    gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)'
  )"
  RUNTIME_SERVICE_ACCOUNT="${project_number}-compute@developer.gserviceaccount.com"
fi

if [[ "$CONFIGURE_SECRETS" == true ]]; then
  "$SCRIPT_DIR/setup-secret-manager.sh" \
    --project "$PROJECT_ID" \
    --region "$REGION" \
    --service "$SERVICE" \
    --runtime-service-account "$RUNTIME_SERVICE_ACCOUNT"
fi

secret_ids=(
  vlegal-database-url
  vlegal-neo4j-password
  vlegal-gemini-api-key
  vlegal-tavily-key
  vlegal-oidc-client-id
  vlegal-oidc-client-secret
  vlegal-session-secret
  vlegal-message-key
)

for secret_id in "${secret_ids[@]}"; do
  enabled_version="$(
    gcloud secrets versions list "$secret_id" \
      --project="$PROJECT_ID" \
      --filter='state=ENABLED' \
      --limit=1 \
      --format='value(name)' \
      2>/dev/null || true
  )"
  if [[ -z "$enabled_version" ]]; then
    echo "Secret has no enabled version: $secret_id" >&2
    exit 1
  fi
done

API_URL="$(
  gcloud run services describe "$SERVICE" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format='value(status.url)' \
    2>/dev/null || true
)"
if [[ -z "$API_URL" ]]; then
  echo "Cannot resolve the existing Cloud Run URL for $SERVICE." >&2
  exit 1
fi
API_URL="${API_URL%/}"

env_vars="$(
  printf '%s' \
    "^@^APP_ENV=production" \
    "@USE_LOCAL_EMBEDDINGS=false" \
    "@GEMINI_USE_ADC=true" \
    "@GEMINI_PROJECT_ID=$PROJECT_ID" \
    "@GEMINI_MODEL=$GEMINI_MODEL" \
    "@GEMINI_LOCATION=global" \
    "@GEMINI_DATA_POLICY=redact" \
    "@EMBEDDING_PROVIDER=gemini-api" \
    "@EMBEDDING_MODEL=gemini-embedding-001" \
    "@EMBEDDING_LOCATION=$EMBEDDING_LOCATION" \
    "@EMBEDDING_MAX_CONCURRENCY=2" \
    "@EMBEDDING_BATCH_SIZE=20" \
    "@EMBEDDING_MAX_RETRIES=8" \
    "@POSTGRES_VECTOR_SIZE=1024" \
    "@RETRIEVER_BACKEND=hybrid_rag" \
    "@NEO4J_URI=$NEO4J_URI" \
    "@NEO4J_USER=$NEO4J_USER" \
    "@NEO4J_DATABASE=$NEO4J_DATABASE" \
    "@PUBLIC_URL=$API_URL" \
    "@FRONTEND_URL=$FRONTEND_URL" \
    "@OIDC_REDIRECT_URI=$FRONTEND_URL/api/auth/google/callback" \
    "@COOKIE_SECURE=true" \
    "@CORS_ORIGINS=$FRONTEND_URL"
)"

secret_bindings="$(
  printf '%s' \
    'DATABASE_URL=vlegal-database-url:latest,' \
    'NEO4J_PASSWORD=vlegal-neo4j-password:latest,' \
    'GEMINI_API_KEY=vlegal-gemini-api-key:latest,' \
    'TAVILY_API_KEY=vlegal-tavily-key:latest,' \
    'OIDC_CLIENT_ID=vlegal-oidc-client-id:latest,' \
    'OIDC_CLIENT_SECRET=vlegal-oidc-client-secret:latest,' \
    'SESSION_SECRET=vlegal-session-secret:latest,' \
    'MESSAGE_ENCRYPTION_KEY=vlegal-message-key:latest'
)"

# A variable cannot change directly from a literal value to a Secret Manager
# reference in one gcloud mutation. Detect only legacy literal bindings and
# remove them in a no-traffic revision before attaching the secret references.
# Existing secret-backed variables are left untouched, making reruns idempotent.
secret_env_names='DATABASE_URL,NEO4J_PASSWORD,GEMINI_API_KEY,TAVILY_API_KEY,OIDC_CLIENT_ID,OIDC_CLIENT_SECRET,SESSION_SECRET,MESSAGE_ENCRYPTION_KEY'
plain_secret_envs="$(
  gcloud run services describe "$SERVICE" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format=json |
    SECRET_ENV_NAMES="$secret_env_names" python3 -c '
import json
import os
import sys

service = json.load(sys.stdin)
spec = service.get("spec") or {}
template = spec.get("template") or {}
container_spec = template.get("spec") or template
containers = container_spec.get("containers") or []
env = containers[0].get("env") or [] if containers else []
wanted = os.environ["SECRET_ENV_NAMES"].split(",")
literal_names = {
    item.get("name")
    for item in env
    if isinstance(item, dict) and "value" in item
}
print(",".join(name for name in wanted if name in literal_names))
'
)"

if [[ -n "$plain_secret_envs" ]]; then
  echo
  echo "Migrating legacy plaintext environment variables to Secret Manager:"
  echo "$plain_secret_envs"
  gcloud run services update "$SERVICE" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --remove-env-vars="$plain_secret_envs" \
    --no-traffic \
    --no-deploy-health-check \
    --quiet
fi

# Pin the supported runtime while allowing the entrypoint buildpack to read the
# Procfile. GOOGLE_ENTRYPOINT must not be set here because it takes precedence
# over Procfile and would omit the migrate/reindex process types from the image.
build_env_vars='GOOGLE_PYTHON_VERSION=3.13.x'
source_commit="$(git -C "$REPO_ROOT" rev-parse --short=8 HEAD)"
deploy_tag="buildpacks-$source_commit"

latest_build_id() {
  gcloud builds list \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --limit=1 \
    --format='value(id)' \
    2>/dev/null || true
}

echo
echo "Deploying $SERVICE from commit $source_commit"
echo "Runtime service account: $RUNTIME_SERVICE_ACCOUNT"
echo "Frontend origin: $FRONTEND_URL"

build_before="$(latest_build_id)"
if ! gcloud run deploy "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --source="$REPO_ROOT" \
  --execution-environment=gen2 \
  --service-account="$RUNTIME_SERVICE_ACCOUNT" \
  --port=8080 \
  --allow-unauthenticated \
  --no-traffic \
  --tag="$deploy_tag" \
  --remove-build-env-vars=GOOGLE_ENTRYPOINT \
  --update-build-env-vars="$build_env_vars" \
  --update-env-vars="$env_vars" \
  --update-secrets="$secret_bindings"; then
  latest_build="$(latest_build_id)"
  if [[ -n "$latest_build" && "$latest_build" != "$build_before" ]]; then
    echo
    echo "Build failed. Read its log with:"
    echo "gcloud beta builds log $latest_build --region=$REGION --project=$PROJECT_ID"
  else
    echo
    echo "Deployment stopped before a new Cloud Build was created."
    echo "Read the gcloud validation error above."
  fi
  exit 1
fi

revision="$(
  gcloud run services describe "$SERVICE" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format='value(status.latestReadyRevisionName)'
)"

tag_url() {
  gcloud run services describe "$SERVICE" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format=json |
    DEPLOY_TAG="$deploy_tag" python3 -c '
import json
import os
import sys

service = json.load(sys.stdin)
tag = os.environ["DEPLOY_TAG"]
for target in (service.get("status") or {}).get("traffic") or []:
    if target.get("tag") == tag:
        print(target.get("url") or "")
        break
'
}

TAG_URL=""
for attempt in {1..12}; do
  TAG_URL="$(tag_url)"
  if [[ -n "$TAG_URL" ]]; then
    break
  fi
  sleep 5
done
if [[ -z "$TAG_URL" ]]; then
  echo "Cannot resolve the no-traffic test URL for tag $deploy_tag." >&2
  exit 1
fi

check_health() {
  local base_url="$1"
  local path="$2"
  local attempt
  for attempt in {1..12}; do
    if curl --fail --silent --show-error --max-time 20 "$base_url$path"; then
      echo
      return 0
    fi
    sleep 10
  done
  echo "Health check failed: $base_url$path" >&2
  return 1
}

echo
echo "Checking the new no-traffic revision at $TAG_URL"
check_health "$TAG_URL" /api/health/live
check_health "$TAG_URL" /api/health/ready

gcloud run services update-traffic "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --to-latest \
  --quiet

gcloud run services update-traffic "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --remove-tags="$deploy_tag" \
  --quiet || echo "Warning: could not remove temporary tag $deploy_tag." >&2

API_URL="$(
  gcloud run services describe "$SERVICE" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format='value(status.url)'
)"
check_health "$API_URL" /api/health/live

echo
echo "Deployment complete."
echo "Revision: $revision"
echo "API URL: $API_URL"
echo "Frontend URL: $FRONTEND_URL"
