#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$SCRIPT_DIR/../compose.production.yml" ]]; then
  DEFAULT_COMPOSE_FILE="$SCRIPT_DIR/../compose.production.yml"
else
  DEFAULT_COMPOSE_FILE="$SCRIPT_DIR/compose.production.yml"
fi

COMPOSE_FILE="${COMPOSE_FILE:-$DEFAULT_COMPOSE_FILE}"
ENV_FILE="${ENV_FILE:-$(dirname "$COMPOSE_FILE")/.env.production}"
PROJECT_NAME="${COMPOSE_PROJECT_NAME:-vlegal}"

command -v docker >/dev/null 2>&1 || {
  echo "Docker is not installed." >&2
  exit 1
}
docker compose version >/dev/null

[[ -f "$COMPOSE_FILE" ]] || {
  echo "Missing Compose file: $COMPOSE_FILE" >&2
  exit 1
}
[[ -f "$ENV_FILE" ]] || {
  echo "Missing environment file: $ENV_FILE" >&2
  echo "Copy .env.production.example to .env.production and fill in every secret." >&2
  exit 1
}

if grep -Eq '=(change-me|replace-with|your-|legal\.example\.com|admin@example\.com)' "$ENV_FILE"; then
  echo "Refusing to deploy because $ENV_FILE still contains example values." >&2
  exit 1
fi

export APP_ENV_FILE="$ENV_FILE"
compose=(docker compose --project-name "$PROJECT_NAME" --env-file "$ENV_FILE" -f "$COMPOSE_FILE")

"${compose[@]}" config --quiet

if [[ "${PULL_IMAGE:-0}" == "1" ]]; then
  "${compose[@]}" pull model-init migrate reindex api frontend worker beat
else
  "${compose[@]}" build --pull model-init migrate reindex api frontend worker beat
fi

"${compose[@]}" up -d --wait --wait-timeout 300 postgres redis neo4j
"${compose[@]}" up --no-deps --abort-on-container-exit --exit-code-from model-init model-init
"${compose[@]}" run --rm --no-deps migrate
"${compose[@]}" up -d --wait --wait-timeout 300 --remove-orphans api frontend worker beat caddy
"${compose[@]}" ps
