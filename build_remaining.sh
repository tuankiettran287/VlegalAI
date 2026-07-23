#!/bin/bash
set -e
PROJECT_ID="project-2c74565e-9f12-4b62-a4e"
REGION="asia-east2"
AR_REPO="vlegal"

build_service() {
  local service=$1
  local dockerfile=$2
  echo "=========================================="
  echo "🚀 Bắt đầu Build Image: ${service}"
  echo "=========================================="
  gcloud builds submit . --project=${PROJECT_ID} --config=<(cat <<CFG
steps:
- name: 'gcr.io/cloud-builders/docker'
  env: ['DOCKER_BUILDKIT=1']
  args: ['build', '-t', '${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${service}:latest', '-f', '${dockerfile}', '.']
images: ['${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${service}:latest']
CFG
)
}

build_service "vlegal-api" "docker/api.Dockerfile"
build_service "vlegal-frontend" "docker/frontend.Dockerfile"

echo "🎉 CHÚC MỪNG! TOÀN BỘ 7 DOCKER IMAGES ĐÃ BUILD HOÀN TẤT 100%!"
