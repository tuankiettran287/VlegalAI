# Deploy VLegalAI lên GCP không cần tên miền

Hướng dẫn này dùng URL mặc định `https://*.run.app` của Cloud Run, không dùng
Caddy, load balancer, DNS hay custom domain. Mỗi tiến trình ứng dụng có một
Dockerfile và một image riêng.

## Kiến trúc GCP

| Image | Tài nguyên GCP | Vai trò |
| --- | --- | --- |
| `vlegal-api` | Cloud Run Service có GPU | FastAPI và Qwen inference |
| `vlegal-frontend` | Cloud Run Service CPU | React SPA và reverse proxy `/api` |
| `vlegal-worker` | Cloud Run Worker Pool có GPU | Celery consumer chạy liên tục |
| `vlegal-beat` | Cloud Run Worker Pool CPU | Celery scheduler chạy liên tục |
| `vlegal-migrate` | Cloud Run Job | `alembic upgrade head` |
| `vlegal-model-init` | Cloud Run Job | tải Qwen3 và BGE-M3 vào hai bucket Cloud Storage |
| `vlegal-reindex` | Cloud Run Job GPU | embedding lại corpus và đồng bộ Neo4j/pgvector |

PostgreSQL/pgvector nên chạy trên Cloud SQL, Redis trên Memorystore và Neo4j
trên Compute Engine hoặc GKE. Không chạy ba database này bằng Cloud Run vì Cloud
Run không cung cấp persistent block storage/TCP endpoint phù hợp cho chúng.

Frontend gọi API qua chính origin frontend (`/api`). Nginx chuyển tiếp request
sang URL Cloud Run của API, nên browser không cần biết URL backend và cookie OIDC
vẫn là same-site. Sau khi deploy, script tự đặt:

```text
PUBLIC_URL=<frontend-run.app-url>
FRONTEND_URL=<frontend-run.app-url>
CORS_ORIGINS=<frontend-run.app-url>
OIDC_REDIRECT_URI=<frontend-run.app-url>/api/auth/google/callback
```

## Dockerfile riêng

```text
docker/api.Dockerfile
docker/frontend.Dockerfile
docker/worker.Dockerfile
docker/beat.Dockerfile
docker/migrate.Dockerfile
docker/model-init.Dockerfile
docker/reindex.Dockerfile
```

`docker-compose.yml`, `compose.production.yml` và workflow CI đã trỏ trực tiếp
đến các file này. `Dockerfile` ở root chỉ được giữ để tương thích với lệnh build
cũ; deploy mới không dùng file đó.

## 1. Biến dùng chung

Các lệnh dưới đây dành cho PowerShell:

```powershell
cd F:\VlegalAI

$PROJECT_ID = "your-gcp-project-id"
$REGION = "asia-southeast1"
$AR_REPO = "vlegal"
$TAG = git rev-parse --short HEAD
$RUN_SA_NAME = "vlegal-run"
$RUN_SA = "$RUN_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
$MODEL_BUCKET = "$PROJECT_ID-vlegal-qwen3-14b"
$EMBEDDING_BUCKET = "$PROJECT_ID-vlegal-bge-m3"
$CORPUS_BUCKET = "$PROJECT_ID-vlegal-corpus"
$NETWORK = "default"
$SUBNET = "default"
$REDIS_HOST = "10.170.0.3"
$REDIS_PORT = 6379
$REDIS_CA_SECRET = "vlegal-redis-server-ca"
$NEO4J_URI = "neo4j+s://your-neo4j-host:7687"

gcloud auth login
gcloud config set project $PROJECT_ID
```

Cloud Run GPU `nvidia-rtx-pro-6000` hiện cần ít nhất 20 CPU/80 GiB RAM. Script
dùng loại GPU này vì checkpoint Qwen3-14B đầy đủ không vừa L4 24 GB. Chỉ truyền
`-GpuType nvidia-l4` sau khi đã thay bằng checkpoint nhỏ hoặc quantized phù hợp.

## 2. Bootstrap project một lần

```powershell
gcloud services enable `
  run.googleapis.com `
  artifactregistry.googleapis.com `
  secretmanager.googleapis.com `
  storage.googleapis.com `
  compute.googleapis.com `
  sqladmin.googleapis.com `
  redis.googleapis.com `
  pubsub.googleapis.com `
  servicenetworking.googleapis.com

gcloud artifacts repositories create $AR_REPO `
  --repository-format=docker `
  --location=$REGION `
  --description="VLegalAI service images"

gcloud iam service-accounts create $RUN_SA_NAME `
  --display-name="VLegalAI Cloud Run runtime"

gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="serviceAccount:$RUN_SA" `
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="serviceAccount:$RUN_SA" `
  --role="roles/redis.dbConnectionUser"

# Celery dùng Pub/Sub làm broker vì Redis Cluster không phải Celery transport.
gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="serviceAccount:$RUN_SA" `
  --role="roles/pubsub.editor"

gcloud storage buckets create "gs://$MODEL_BUCKET" `
  --location=$REGION `
  --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding "gs://$MODEL_BUCKET" `
  --member="serviceAccount:$RUN_SA" `
  --role="roles/storage.objectUser"

gcloud storage buckets create "gs://$EMBEDDING_BUCKET" `
  --location=$REGION `
  --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding "gs://$EMBEDDING_BUCKET" `
  --member="serviceAccount:$RUN_SA" `
  --role="roles/storage.objectUser"

gcloud storage buckets create "gs://$CORPUS_BUCKET" `
  --location=$REGION `
  --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding "gs://$CORPUS_BUCKET" `
  --member="serviceAccount:$RUN_SA" `
  --role="roles/storage.objectViewer"

gcloud storage rsync ".\Data (1)" "gs://$CORPUS_BUCKET" --recursive
```

Nếu resource đã tồn tại, bỏ qua lỗi `ALREADY_EXISTS`. Network/subnet dùng cho
Direct VPC egress phải nằm cùng region; subnet phải đủ IP cho Cloud Run và Worker
Pool.

## 3. Dịch vụ dữ liệu và Secret Manager

Chuẩn bị các endpoint trước khi deploy:

```text
DATABASE_URL=postgresql+asyncpg://vlegal:<password>@<cloud-sql-private-ip>:5432/vlegal
REDIS_URL=rediss://10.170.0.3:6379/0
REDIS_CLUSTER_MODE=true
REDIS_IAM_AUTH=true
REDIS_CA_CERTS=/var/run/secrets/redis/server-ca.pem
NEO4J_URI=neo4j+s://<neo4j-host>:7687
```

Redis này là Memorystore for Redis Cluster qua PSC, bật IAM Auth và TLS. API và
worker dùng Redis Cluster client cho rate limit/cache/lock. Celery dùng Google
Pub/Sub làm broker vì Redis Cluster chỉ hỗ trợ database `0` và Celery không có
Redis Cluster transport.

Upload CA đã tải từ Memorystore vào Secret Manager. File `server-ca.pem` bị bỏ
qua bởi Git và Docker build; Cloud Run mount certificate thành file lúc chạy:

```powershell
gcloud secrets create $REDIS_CA_SECRET `
  --replication-policy=automatic `
  --data-file=server-ca.pem

# Nếu secret đã tồn tại, chỉ thêm version mới:
gcloud secrets versions add $REDIS_CA_SECRET --data-file=server-ca.pem
```

Tạo các secret dưới đây trong Secret Manager và thêm ít nhất một version:

```text
vlegal-database-url
vlegal-redis-server-ca
vlegal-neo4j-password
vlegal-session-secret
vlegal-message-key
vlegal-oidc-client-id
vlegal-oidc-client-secret
vlegal-tavily-key
```

Không đưa secret vào source, image tag hoặc tham số `--set-env-vars`. Giá trị
`vlegal-message-key` là khóa Fernet; có thể tạo offline bằng:

```powershell
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 4. Build và push từng image

Script build dùng đúng Dockerfile của từng service và mặc định target
`linux/amd64`, là kiến trúc Cloud Run hỗ trợ:

```powershell
# Build + push toàn bộ bảy image
.\scripts\gcp\build-images.ps1 `
  -ProjectId $PROJECT_ID -Region $REGION -Repository $AR_REPO -Tag $TAG -Push
```

Build/push riêng từng service:

```powershell
.\scripts\gcp\build-images.ps1 -ProjectId $PROJECT_ID -Tag $TAG -Service api -Push
.\scripts\gcp\build-images.ps1 -ProjectId $PROJECT_ID -Tag $TAG -Service frontend -Push
.\scripts\gcp\build-images.ps1 -ProjectId $PROJECT_ID -Tag $TAG -Service worker -Push
.\scripts\gcp\build-images.ps1 -ProjectId $PROJECT_ID -Tag $TAG -Service beat -Push
.\scripts\gcp\build-images.ps1 -ProjectId $PROJECT_ID -Tag $TAG -Service migrate -Push
.\scripts\gcp\build-images.ps1 -ProjectId $PROJECT_ID -Tag $TAG -Service model-init -Push
.\scripts\gcp\build-images.ps1 -ProjectId $PROJECT_ID -Tag $TAG -Service reindex -Push
```

Image được push theo dạng:

```text
asia-southeast1-docker.pkg.dev/<project>/vlegal/vlegal-<service>:<git-sha>
```

## 5. Deploy từng service/job lên GCP

Chạy lần lượt theo thứ tự sau. `-ExecuteJobs` deploy rồi thực thi job; bỏ flag đó
nếu chỉ muốn cập nhật cấu hình job mà chưa chạy.

### 5.1 Tải model

```powershell
.\scripts\gcp\deploy.ps1 `
  -ProjectId $PROJECT_ID -Region $REGION -Repository $AR_REPO -Tag $TAG `
  -ModelBucket $MODEL_BUCKET -EmbeddingBucket $EMBEDDING_BUCKET `
  -Neo4jUri $NEO4J_URI `
  -Component model-init -ExecuteJobs
```

Hai Cloud Storage bucket được mount read-write vào job ở `/models/qwen3` và
`/models/embedding`. API/worker mount lại read-only. Job có marker nên chạy lại
không tải checkpoint nếu repo/revision không thay đổi.

### 5.2 Migration

```powershell
.\scripts\gcp\deploy.ps1 `
  -ProjectId $PROJECT_ID -Region $REGION -Repository $AR_REPO -Tag $TAG `
  -Network $NETWORK -Subnet $SUBNET -Neo4jUri $NEO4J_URI `
  -Component migrate -ExecuteJobs
```

### 5.3 Re-index embedding

Trước khi deploy API lần đầu, chạy job tạo lại embedding. Migration
`20260721_0003` chủ động xoá vector hash cũ vì không thể đổi trực tiếp sang
BGE-M3; job này tạo vector chuẩn hoá 1024 chiều từ corpus và dùng lại chính vector
đó khi ghi vào PostgreSQL:

```powershell
.\scripts\gcp\deploy.ps1 `
  -ProjectId $PROJECT_ID -Region $REGION -Repository $AR_REPO -Tag $TAG `
  -EmbeddingBucket $EMBEDDING_BUCKET -CorpusBucket $CORPUS_BUCKET `
  -Network $NETWORK -Subnet $SUBNET -Neo4jUri $NEO4J_URI `
  -Component reindex -ExecuteJobs
```

Job re-index dùng image riêng `vlegal-reindex`, một L4 trong thời gian chạy, BGE-M3 từ
bucket chỉ đọc và corpus từ `$CORPUS_BUCKET`. File SQLite trung gian nằm trong
filesystem tạm của job; dữ liệu lâu dài được ghi vào Cloud SQL/pgvector và Neo4j.

### 5.4 API

```powershell
.\scripts\gcp\deploy.ps1 `
  -ProjectId $PROJECT_ID -Region $REGION -Repository $AR_REPO -Tag $TAG `
  -ModelBucket $MODEL_BUCKET -EmbeddingBucket $EMBEDDING_BUCKET `
  -Network $NETWORK -Subnet $SUBNET `
  -RedisHost $REDIS_HOST -RedisPort $REDIS_PORT -RedisCaSecret $REDIS_CA_SECRET `
  -Neo4jUri $NEO4J_URI -Component api
```

API được public để Nginx frontend có thể reverse proxy đến nó. API nghiệp vụ vẫn
áp dụng session/role/rate-limit ở tầng ứng dụng; chỉ các endpoint được thiết kế
public mới không cần đăng nhập.

### 5.5 Frontend

```powershell
.\scripts\gcp\deploy.ps1 `
  -ProjectId $PROJECT_ID -Region $REGION -Repository $AR_REPO -Tag $TAG `
  -Neo4jUri $NEO4J_URI -Component frontend
```

Script đọc URL API, đặt `API_UPSTREAM`, lấy URL frontend và cập nhật bốn biến URL
của API. Không có bước cấu hình domain.

### 5.6 Worker

```powershell
.\scripts\gcp\deploy.ps1 `
  -ProjectId $PROJECT_ID -Region $REGION -Repository $AR_REPO -Tag $TAG `
  -ModelBucket $MODEL_BUCKET -EmbeddingBucket $EMBEDDING_BUCKET `
  -Network $NETWORK -Subnet $SUBNET `
  -RedisHost $REDIS_HOST -RedisPort $REDIS_PORT -RedisCaSecret $REDIS_CA_SECRET `
  -Neo4jUri $NEO4J_URI -Component worker
```

### 5.7 Beat

```powershell
.\scripts\gcp\deploy.ps1 `
  -ProjectId $PROJECT_ID -Region $REGION -Repository $AR_REPO -Tag $TAG `
  -Network $NETWORK -Subnet $SUBNET -Neo4jUri $NEO4J_URI `
  -Component beat
```

Worker Pool không autoscale và `worker` giữ một GPU hoạt động liên tục. Nếu chỉ
cần refresh kho luật theo ngày, nên chuyển tác vụ này thành Cloud Run Job + Cloud
Scheduler để giảm chi phí; cấu hình hiện tại giữ nguyên semantics Celery đang có.

### Deploy tất cả bằng một lệnh

Sau khi dữ liệu, bucket và secrets đã sẵn sàng:

```powershell
.\scripts\gcp\deploy.ps1 `
  -ProjectId $PROJECT_ID -Region $REGION -Repository $AR_REPO -Tag $TAG `
  -RunServiceAccount $RUN_SA -ModelBucket $MODEL_BUCKET `
  -EmbeddingBucket $EMBEDDING_BUCKET -CorpusBucket $CORPUS_BUCKET `
  -Network $NETWORK -Subnet $SUBNET -Neo4jUri $NEO4J_URI `
  -RedisHost $REDIS_HOST -RedisPort $REDIS_PORT -RedisCaSecret $REDIS_CA_SECRET `
  -Component all -ExecuteJobs
```

## 6. Lấy URL và cấu hình Google OAuth

```powershell
$FRONTEND_URL = gcloud run services describe vlegal-frontend `
  --project=$PROJECT_ID --region=$REGION --format="value(status.url)"

$API_URL = gcloud run services describe vlegal-api `
  --project=$PROJECT_ID --region=$REGION --format="value(status.url)"

Write-Output "Frontend: $FRONTEND_URL"
Write-Output "API:      $API_URL"
Write-Output "OAuth:    $FRONTEND_URL/api/auth/google/callback"
```

Trong Google OAuth client loại **Web application**, thêm:

```text
Authorized JavaScript origin: <FRONTEND_URL>
Authorized redirect URI:      <FRONTEND_URL>/api/auth/google/callback
```

Đây là cấu hình URL `run.app`, không phải custom domain.

## 7. Lệnh chạy từng Docker ở local

Tạo `.env` trước:

```powershell
Copy-Item .env.example .env
```

Build riêng từng image:

```powershell
docker build -f docker/api.Dockerfile -t vlegal-api:local .
docker build -f docker/frontend.Dockerfile -t vlegal-frontend:local .
docker build -f docker/worker.Dockerfile -t vlegal-worker:local .
docker build -f docker/beat.Dockerfile -t vlegal-beat:local .
docker build -f docker/migrate.Dockerfile -t vlegal-migrate:local .
docker build -f docker/model-init.Dockerfile -t vlegal-model-init:local .
docker build -f docker/reindex.Dockerfile -t vlegal-reindex:local .
```

Khởi động hạ tầng local trước:

```powershell
docker compose up -d postgres redis neo4j
```

Chạy từng service/job độc lập qua Compose:

```powershell
# Job một lần
docker compose run --rm model-init
docker compose run --rm migrate
docker compose --profile jobs run --rm reindex --reset-postgres --reset-neo4j

# Service chạy nền
docker compose up -d api
docker compose up -d frontend
docker compose up -d worker
docker compose up -d beat
```

Hoặc chạy toàn bộ stack:

```powershell
docker compose up -d --build
```

Xem log và dừng riêng từng service:

```powershell
docker compose logs -f api
docker compose stop api
docker compose rm -f api
```

Thay `api` bằng `frontend`, `worker` hoặc `beat` khi cần.

## 8. Kiểm tra sau deploy

```powershell
curl.exe -fsS "$API_URL/api/health/live"
curl.exe -fsS "$API_URL/api/health/ready"
curl.exe -I "$FRONTEND_URL/"

gcloud run services logs read vlegal-api `
  --project=$PROJECT_ID --region=$REGION --limit=200
```

Các file/scripts trong thay đổi này chỉ tạo cấu hình; không tự build image, chạy
container hay deploy tài nguyên khi checkout source.

## Tài liệu GCP liên quan

- [Cloud Run container runtime contract](https://docs.cloud.google.com/run/docs/container-contract)
- [Deploy Cloud Run worker pools](https://docs.cloud.google.com/run/docs/deploy-worker-pools)
- [Cloud Run GPU services](https://docs.cloud.google.com/run/docs/configuring/services/gpu)
- [Cloud Run GPU worker pools](https://docs.cloud.google.com/run/docs/configuring/workerpools/gpu)
- [Cloud Storage volume mounts](https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts)
- [Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc)
