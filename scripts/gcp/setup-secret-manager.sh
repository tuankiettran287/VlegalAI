#!/usr/bin/env bash
#
# Store VLegal AI production credentials in Google Secret Manager without
# putting secret values in shell history, process arguments, or repository files.
set -Eeuo pipefail
umask 077

PROJECT_ID="${GOOGLE_CLOUD_PROJECT:-}"
REGION="${GCP_REGION:-asia-southeast1}"
SERVICE="${GCP_API_SERVICE:-vlegal-api}"
RUNTIME_SERVICE_ACCOUNT="${GCP_RUN_SERVICE_ACCOUNT:-}"

usage() {
  cat <<'EOF'
Usage:
  ./scripts/gcp/setup-secret-manager.sh [options]

Options:
  --project PROJECT_ID
  --region REGION
  --service SERVICE_NAME
  --runtime-service-account SERVICE_ACCOUNT_EMAIL
  -h, --help

Values are read from /dev/tty with echo disabled. If a secret already has an
enabled version, press Enter to keep it. SESSION_SECRET and
MESSAGE_ENCRYPTION_KEY are generated when they do not exist and input is blank.
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
    --runtime-service-account)
      RUNTIME_SERVICE_ACCOUNT="${2:?Missing value for --runtime-service-account}"
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

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Required command not found: $1" >&2
    exit 1
  fi
}

require_command gcloud
require_command openssl

if [[ -z "$PROJECT_ID" ]]; then
  PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
fi
if [[ -z "$PROJECT_ID" || "$PROJECT_ID" == "(unset)" ]]; then
  echo "Set --project or GOOGLE_CLOUD_PROJECT." >&2
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

echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Cloud Run service: $SERVICE"
echo "Runtime service account: $RUNTIME_SERVICE_ACCOUNT"
echo

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  aiplatform.googleapis.com \
  --project="$PROJECT_ID" \
  --quiet

secret_exists() {
  gcloud secrets describe "$1" --project="$PROJECT_ID" >/dev/null 2>&1
}

secret_has_enabled_version() {
  [[ -n "$(
    gcloud secrets versions list "$1" \
      --project="$PROJECT_ID" \
      --filter='state=ENABLED' \
      --limit=1 \
      --format='value(name)' \
      2>/dev/null || true
  )" ]]
}

generate_session_secret() {
  openssl rand -base64 48 | tr -d '\r\n'
}

generate_message_key() {
  openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\r\n'
}

configure_secret() {
  local variable_name="$1"
  local secret_id="$2"
  local generator="${3:-}"
  local has_enabled=false
  local prompt_suffix="required"
  local value=""

  if secret_exists "$secret_id" && secret_has_enabled_version "$secret_id"; then
    has_enabled=true
    prompt_suffix="Enter keeps the current version"
  elif [[ -n "$generator" ]]; then
    prompt_suffix="Enter generates a value"
  fi

  printf '%s (%s): ' "$variable_name" "$prompt_suffix" >/dev/tty
  IFS= read -r -s value </dev/tty
  printf '\n' >/dev/tty

  if [[ -z "$value" ]]; then
    if [[ "$has_enabled" == true ]]; then
      echo "[KEEP] $secret_id"
      return
    fi
    case "$generator" in
      session)
        value="$(generate_session_secret)"
        ;;
      message)
        value="$(generate_message_key)"
        ;;
      *)
        echo "A value is required for $variable_name because $secret_id has no enabled version." >&2
        exit 1
        ;;
    esac
  fi

  if secret_exists "$secret_id"; then
    printf '%s' "$value" |
      gcloud secrets versions add "$secret_id" \
        --project="$PROJECT_ID" \
        --data-file=- \
        --quiet >/dev/null
  else
    printf '%s' "$value" |
      gcloud secrets create "$secret_id" \
        --project="$PROJECT_ID" \
        --replication-policy=automatic \
        --data-file=- \
        --quiet >/dev/null
  fi
  value=""
  unset value
  echo "[OK] $secret_id"
}

configure_secret DATABASE_URL vlegal-database-url
configure_secret NEO4J_PASSWORD vlegal-neo4j-password
configure_secret TAVILY_API_KEY vlegal-tavily-key
configure_secret OIDC_CLIENT_ID vlegal-oidc-client-id
configure_secret OIDC_CLIENT_SECRET vlegal-oidc-client-secret
configure_secret SESSION_SECRET vlegal-session-secret session
configure_secret MESSAGE_ENCRYPTION_KEY vlegal-message-key message

secret_ids=(
  vlegal-database-url
  vlegal-neo4j-password
  vlegal-tavily-key
  vlegal-oidc-client-id
  vlegal-oidc-client-secret
  vlegal-session-secret
  vlegal-message-key
)

for secret_id in "${secret_ids[@]}"; do
  gcloud secrets add-iam-policy-binding "$secret_id" \
    --project="$PROJECT_ID" \
    --member="serviceAccount:$RUNTIME_SERVICE_ACCOUNT" \
    --role='roles/secretmanager.secretAccessor' \
    --condition=None \
    --quiet >/dev/null
done

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$RUNTIME_SERVICE_ACCOUNT" \
  --role='roles/aiplatform.user' \
  --condition=None \
  --quiet >/dev/null

echo
echo "Secret Manager is ready. No secret values were written to disk or printed."
