#!/usr/bin/env bash
#
# Rebuild and publish the VLegal GraphRAG index with the latest healthy API
# image. Gemini generation and embeddings both use Vertex AI with ADC. Bulk
# embedding progress is checkpointed in PostgreSQL across task attempts.
set -Eeuo pipefail

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-}"
REGION="${GCP_REGION:-asia-southeast1}"
SERVICE="${GCP_API_SERVICE:-vlegal-api}"
JOB="${GCP_REINDEX_JOB:-vlegal-reindex}"
MIGRATION_JOB="${GCP_MIGRATION_JOB:-vlegal-migrate}"
RUNTIME_SERVICE_ACCOUNT="${GCP_RUN_SERVICE_ACCOUNT:-}"
NEO4J_URI="${NEO4J_URI:-}"
NEO4J_USER="${NEO4J_USER:-neo4j}"
NEO4J_DATABASE="${NEO4J_DATABASE:-neo4j}"
CPU="${REINDEX_CPU:-4}"
MEMORY="${REINDEX_MEMORY:-8Gi}"
EMBEDDING_LOCATION="${GCP_EMBEDDING_LOCATION:-asia-southeast1}"
EMBEDDING_VERTEX_LOCATIONS="${EMBEDDING_VERTEX_LOCATIONS:-asia-east1|asia-east2|asia-northeast1|asia-northeast3|asia-south1|asia-southeast1|australia-southeast1|europe-central2|europe-north1|europe-southwest1|europe-west1|europe-west2|europe-west3|europe-west4|europe-west6|europe-west8|europe-west9|me-central1|me-central2|me-west1|northamerica-northeast1|southamerica-east1|us-central1|us-east1|us-east4|us-east5|us-south1|us-west1|us-west4}"
EMBEDDING_VERTEX_REQUESTS_PER_MINUTE="${EMBEDDING_VERTEX_REQUESTS_PER_MINUTE:-4.5}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/gcp/run-reindex-buildpacks.sh [options]

Required:
  --project PROJECT_ID
  --neo4j-uri NEO4J_URI

Options:
  --region REGION                         (default: asia-southeast1)
  --service SERVICE_NAME                  (default: vlegal-api)
  --job JOB_NAME                          (default: vlegal-reindex)
  --migration-job JOB_NAME                (default: vlegal-migrate)
  --runtime-service-account EMAIL         (default: API service identity)
  --neo4j-user USER                       (default: neo4j)
  --neo4j-database DATABASE               (default: neo4j)
  --cpu CPU                               (default: 4)
  --memory MEMORY                         (default: 8Gi)
  --embedding-location REGION             (default: asia-southeast1)
  -h, --help
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
    --job)
      JOB="${2:?Missing value for --job}"
      shift 2
      ;;
    --migration-job)
      MIGRATION_JOB="${2:?Missing value for --migration-job}"
      shift 2
      ;;
    --runtime-service-account)
      RUNTIME_SERVICE_ACCOUNT="${2:?Missing value for --runtime-service-account}"
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
    --cpu)
      CPU="${2:?Missing value for --cpu}"
      shift 2
      ;;
    --memory)
      MEMORY="${2:?Missing value for --memory}"
      shift 2
      ;;
    --embedding-location)
      EMBEDDING_LOCATION="${2:?Missing value for --embedding-location}"
      shift 2
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

if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "Set --project or GOOGLE_CLOUD_PROJECT." >&2
  exit 1
fi
if [[ -z "$NEO4J_URI" ]]; then
  echo "--neo4j-uri or NEO4J_URI is required." >&2
  exit 1
fi

for command_name in gcloud curl; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command not found: $command_name" >&2
    exit 1
  fi
done

revision="$(
  gcloud run services describe "$SERVICE" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format='value(status.latestReadyRevisionName)'
)"
image="$(
  gcloud run revisions describe "$revision" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format='value(spec.containers[0].image)'
)"
if [[ -z "$revision" || -z "$image" ]]; then
  echo "Cannot resolve the latest healthy image for $SERVICE." >&2
  exit 1
fi

if [[ -z "$RUNTIME_SERVICE_ACCOUNT" ]]; then
  RUNTIME_SERVICE_ACCOUNT="$(
    gcloud run services describe "$SERVICE" \
      --project="$PROJECT_ID" \
      --region="$REGION" \
      --format='value(spec.template.spec.serviceAccountName)'
  )"
fi

for secret_id in \
  vlegal-database-url \
  vlegal-neo4j-password
do
  enabled_version="$(
    gcloud secrets versions list "$secret_id" \
      --project="$PROJECT_ID" \
      --filter='state=ENABLED' \
      --limit=1 \
      --format='value(name)'
  )"
  if [[ -z "$enabled_version" ]]; then
    echo "Secret has no enabled version: $secret_id" >&2
    exit 1
  fi
done

env_vars="$(
  printf '%s' \
    "^@^APP_ENV=production" \
    "@GEMINI_USE_ADC=true" \
    "@GEMINI_PROJECT_ID=$PROJECT_ID" \
    "@GEMINI_DATA_POLICY=redact" \
    "@EMBEDDING_PROVIDER=vertex" \
    "@EMBEDDING_MODEL=gemini-embedding-001" \
    "@EMBEDDING_LOCATION=$EMBEDDING_LOCATION" \
    "@EMBEDDING_VERTEX_LOCATIONS=$EMBEDDING_VERTEX_LOCATIONS" \
    "@EMBEDDING_VERTEX_REQUESTS_PER_MINUTE=$EMBEDDING_VERTEX_REQUESTS_PER_MINUTE" \
    "@EMBEDDING_MAX_CONCURRENCY=32" \
    "@EMBEDDING_BATCH_SIZE=20" \
    "@EMBEDDING_TIMEOUT_SECONDS=120" \
    "@EMBEDDING_MAX_RETRIES=8" \
    "@LEGAL_EMBEDDING_CHECKPOINT_ENABLED=true" \
    "@LEGAL_EMBEDDING_CHECKPOINT_BATCH_SIZE=640" \
    "@POSTGRES_VECTOR_SIZE=1024" \
    "@NEO4J_URI=$NEO4J_URI" \
    "@NEO4J_USER=$NEO4J_USER" \
    "@NEO4J_DATABASE=$NEO4J_DATABASE" \
    "@LEGAL_DATA_DIR=/workspace/Data (1)" \
    "@LEGAL_STORAGE_DIR=/tmp/graphrag" \
    "@LEGAL_GRAPHRAG_DB=/tmp/graphrag/legal_graphrag.sqlite"
)"

echo "API revision: $revision"
echo "Image: $image"
echo "Applying PostgreSQL migrations with $MIGRATION_JOB."

gcloud run jobs deploy "$MIGRATION_JOB" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$image" \
  --service-account="$RUNTIME_SERVICE_ACCOUNT" \
  --command=/cnb/process/migrate \
  --args="" \
  --set-secrets=DATABASE_URL=vlegal-database-url:latest \
  --cpu=1 \
  --memory=1Gi \
  --task-timeout=15m \
  --max-retries=1 \
  --tasks=1 \
  --quiet

gcloud run jobs execute "$MIGRATION_JOB" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --wait

echo "Deploying and executing $JOB with Vertex AI checkpoints."

gcloud run jobs deploy "$JOB" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --image="$image" \
  --service-account="$RUNTIME_SERVICE_ACCOUNT" \
  --command=/cnb/process/reindex \
  --args="" \
  --set-secrets=DATABASE_URL=vlegal-database-url:latest,NEO4J_PASSWORD=vlegal-neo4j-password:latest \
  --set-env-vars="$env_vars" \
  --cpu="$CPU" \
  --memory="$MEMORY" \
  --task-timeout=24h \
  --max-retries=3 \
  --tasks=1 \
  --quiet

if ! gcloud run jobs execute "$JOB" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --task-timeout=24h \
  --wait; then
  echo
  echo "Reindex stopped before completion. Completed Vertex embeddings are safe"
  echo "in PostgreSQL. Run this same script again to resume from the checkpoint."
  exit 1
fi

data_revision="$(date -u +%Y%m%d%H%M%S)"
gcloud run services update "$SERVICE" \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --update-env-vars="DATA_REVISION=$data_revision" \
  --quiet

api_url="$(
  gcloud run services describe "$SERVICE" \
    --project="$PROJECT_ID" \
    --region="$REGION" \
    --format='value(status.url)'
)"
curl --fail --silent --show-error --max-time 30 \
  "$api_url/api/health/live"
echo
curl --fail --silent --show-error --max-time 30 \
  "$api_url/api/health/ready"
echo
echo "Reindex complete. API data revision: $data_revision"
