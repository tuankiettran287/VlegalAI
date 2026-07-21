# Deploy VLegalAI lên Google Cloud Run

Tài liệu này deploy **container API/frontend** lên Cloud Run. Không dùng
`docker-compose.yml` trên Cloud Run: PostgreSQL, Redis, Neo4j và Qdrant phải chạy
ở dịch vụ bên ngoài; Caddy không cần vì Cloud Run đã cung cấp HTTPS.

## 1. Kiến trúc đích

| Thành phần local | Thành phần trên GCP |
| --- | --- |
| `api` + frontend | Một Cloud Run service |
| `model-init` | Một Cloud Run Job chạy một lần |
| volume `qwen_model` | Cloud Storage bucket mount read-only |
| PostgreSQL | Cloud SQL for PostgreSQL |
| Redis | Memorystore for Redis |
| Neo4j | Neo4j Aura hoặc Neo4j trên GCE/GKE |
| Qdrant | Qdrant Cloud hoặc Qdrant trên GCE/GKE |
| `migrate` | Cloud Run Job chạy trước mỗi release |
| Caddy | Không dùng; Cloud Run terminate HTTPS |

Cloud Run không giữ file ghi vào filesystem sau khi instance dừng. Vì vậy không
được tải checkpoint 27,52 GiB vào filesystem của container lúc startup. Bucket
Cloud Storage được mount như thư mục `/models/qwen3`; model chỉ cần tải vào bucket
một lần. Xem [container runtime contract](https://docs.cloud.google.com/run/docs/container-contract)
và [Cloud Storage volume mounts](https://docs.cloud.google.com/run/docs/configuring/services/cloud-storage-volume-mounts).

### Chọn GPU

Checkpoint `Qwen/Qwen3-14B` hiện tại không phù hợp với L4 24 GB ở dạng BF16 đầy
đủ. Hướng dẫn dưới đây dùng `nvidia-rtx-pro-6000` 96 GB tại Singapore. Cloud Run
yêu cầu tối thiểu 20 CPU và 80 GiB RAM cho GPU này. Nếu chi phí quá cao, cần đổi
sang checkpoint quantized hoặc model nhỏ rồi mới chọn `nvidia-l4`.

Danh sách GPU/region hiện hành nằm tại
[Cloud Run GPU support](https://docs.cloud.google.com/run/docs/configuring/services/gpu).

## 2. Chuẩn bị project và Artifact Registry

Các lệnh dưới đây dành cho PowerShell. Thay giá trị mẫu trước khi chạy:

```powershell
$PROJECT_ID = "your-gcp-project-id"
$REGION = "asia-southeast1"
$AR_REPO = "vlegal"
$SERVICE = "vlegal-api"
$MODEL_JOB = "vlegal-model-init"
$MIGRATE_JOB = "vlegal-migrate"
$MODEL_BUCKET = "$PROJECT_ID-vlegal-qwen3-14b"
$NETWORK = "default"
$SUBNET = "default"
$IMAGE_TAG = git rev-parse --short HEAD
$IMAGE = "$REGION-docker.pkg.dev/$PROJECT_ID/$AR_REPO/vlegal-ai:$IMAGE_TAG"
$RUN_SA_NAME = "vlegal-run"
$RUN_SA = "$RUN_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"

gcloud auth login
gcloud config set project $PROJECT_ID

gcloud services enable `
  run.googleapis.com `
  artifactregistry.googleapis.com `
  cloudbuild.googleapis.com `
  secretmanager.googleapis.com `
  sqladmin.googleapis.com `
  redis.googleapis.com `
  compute.googleapis.com `
  storage.googleapis.com

gcloud artifacts repositories create $AR_REPO `
  --repository-format=docker `
  --location=$REGION `
  --description="VLegalAI container images"

gcloud iam service-accounts create $RUN_SA_NAME `
  --display-name="VLegalAI Cloud Run"
```

Nếu repository hoặc service account đã tồn tại, bỏ qua lỗi `ALREADY_EXISTS`.
Artifact Registry phải được tạo trước khi push image. Xem
[Artifact Registry Docker quickstart](https://docs.cloud.google.com/artifact-registry/docs/docker/store-docker-container-images).

## 3. Tạo các dịch vụ dữ liệu

Tạo trong cùng region `asia-southeast1`:

1. Cloud SQL PostgreSQL 16, database `vlegal`, user riêng cho ứng dụng, private IP.
2. Memorystore Redis trong cùng VPC.
3. Neo4j Aura và Qdrant Cloud, hoặc tự host chúng trên GCE/GKE với private IP.

Cloud Run kết nối các địa chỉ private bằng Direct VPC egress. Google khuyến nghị
Direct VPC cho Memorystore vì độ trễ/chi phí tốt hơn connector. Tham khảo
[Cloud Run → Memorystore](https://docs.cloud.google.com/memorystore/docs/redis/connect-redis-instance-cloud-run),
[Direct VPC egress](https://docs.cloud.google.com/run/docs/configuring/vpc-direct-vpc)
và [Cloud Run → Cloud SQL PostgreSQL](https://docs.cloud.google.com/sql/docs/postgres/connect-run).

Các URL cần chuẩn bị:

```text
DATABASE_URL=postgresql+asyncpg://vlegal:<password>@<cloud-sql-private-ip>:5432/vlegal
REDIS_URL=redis://<memorystore-private-ip>:6379/0
NEO4J_URI=neo4j+s://<neo4j-host>:7687
QDRANT_URL=https://<qdrant-host>
```

Không commit các giá trị này. Tạo secrets trong Secret Manager bằng Console hoặc
CLI. Danh sách tối thiểu:

```text
vlegal-database-url
vlegal-redis-url
vlegal-neo4j-password
vlegal-qdrant-api-key
vlegal-session-secret
vlegal-message-key
vlegal-oidc-client-id
vlegal-oidc-client-secret
vlegal-tavily-key
```

Gán quyền đọc secret cho service account:

```powershell
gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="serviceAccount:$RUN_SA" `
  --role="roles/secretmanager.secretAccessor"
```

Cloud Run hỗ trợ đưa Secret Manager secret vào environment variable hoặc file;
xem [Cloud Run secrets](https://docs.cloud.google.com/run/docs/configuring/services/secrets).

## 4. Build và push một container image

Chạy tại `F:\VlegalAI`:

```powershell
cd F:\VlegalAI
gcloud builds submit `
  --timeout=3600s `
  --tag $IMAGE `
  .
```

Image này chứa frontend, API và runtime CUDA, nhưng **không chứa checkpoint**.
Cloud Run import image theo digest cho mỗi revision; nên dùng tag Git SHA, không
dùng duy nhất `latest` cho production. Xem
[deploy container images](https://docs.cloud.google.com/run/docs/deploying).

## 5. Tạo bucket và tải model đúng một lần

```powershell
gcloud storage buckets create "gs://$MODEL_BUCKET" `
  --location=$REGION `
  --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding "gs://$MODEL_BUCKET" `
  --member="serviceAccount:$RUN_SA" `
  --role="roles/storage.objectUser"
```

Deploy `model-init` dưới dạng Cloud Run Job. Image chạy bằng UID/GID `999`, vì vậy
volume mount được đặt cùng UID/GID để job có thể ghi:

```powershell
gcloud run jobs deploy $MODEL_JOB `
  --image=$IMAGE `
  --region=$REGION `
  --service-account=$RUN_SA `
  --command=python `
  --args="scripts/download_qwen_model.py,--output-dir,/models/qwen3" `
  --cpu=4 `
  --memory=8Gi `
  --task-timeout=3h `
  --max-retries=3 `
  --set-env-vars="QWEN_MODEL_REPO=Qwen/Qwen3-14B,QWEN_MODEL_REVISION=main,HF_HUB_OFFLINE=0,TRANSFORMERS_OFFLINE=0" `
  --add-volume="mount-path=/models/qwen3,type=cloud-storage,bucket=$MODEL_BUCKET,readonly=false,mount-options=uid=999;gid=999"

gcloud run jobs execute $MODEL_JOB `
  --region=$REGION `
  --wait
```

Job phải kết thúc thành công và log phải có `Download completed` cùng
`Checkpoint is ready`. Các lần chạy sau đọc `.vlegal-model.json` và thoát nhanh,
không tải lại model.

## 6. Chạy migration bằng Cloud Run Job

```powershell
gcloud run jobs deploy $MIGRATE_JOB `
  --image=$IMAGE `
  --region=$REGION `
  --service-account=$RUN_SA `
  --command=alembic `
  --args="upgrade,head" `
  --cpu=1 `
  --memory=1Gi `
  --task-timeout=15m `
  --max-retries=1 `
  --network=$NETWORK `
  --subnet=$SUBNET `
  --vpc-egress=private-ranges-only `
  --set-secrets="DATABASE_URL=vlegal-database-url:latest"

gcloud run jobs execute $MIGRATE_JOB `
  --region=$REGION `
  --wait
```

Chỉ deploy revision API sau khi migration trả thành công.

## 7. Deploy API/frontend lên Cloud Run GPU

Đặt endpoint Neo4j/Qdrant trước khi chạy:

```powershell
$NEO4J_URI = "neo4j+s://your-neo4j-host:7687"
$QDRANT_URL = "https://your-qdrant-host"
```

Deploy container:

```powershell
gcloud run deploy $SERVICE `
  --image=$IMAGE `
  --region=$REGION `
  --execution-environment=gen2 `
  --service-account=$RUN_SA `
  --port=8000 `
  --gpu=1 `
  --gpu-type=nvidia-rtx-pro-6000 `
  --no-gpu-zonal-redundancy `
  --cpu=20 `
  --memory=80Gi `
  --concurrency=1 `
  --min-instances=0 `
  --max-instances=1 `
  --timeout=3600 `
  --no-cpu-throttling `
  --network=$NETWORK `
  --subnet=$SUBNET `
  --vpc-egress=private-ranges-only `
  --allow-unauthenticated `
  --add-volume="mount-path=/models/qwen3,type=cloud-storage,bucket=$MODEL_BUCKET,readonly=true" `
  --set-env-vars="APP_ENV=production,QWEN_MODEL_PATH=/models/qwen3,QWEN_MODEL=Qwen3-14B,QWEN_DEVICE=cuda,QWEN_DTYPE=bfloat16,QWEN_MAX_CONCURRENT_GENERATIONS=1,WEB_CONCURRENCY=1,DATABASE_POOL_SIZE=5,DATABASE_MAX_OVERFLOW=5,RETRIEVER_BACKEND=hybrid_rag,NEO4J_URI=$NEO4J_URI,NEO4J_USER=neo4j,QDRANT_URL=$QDRANT_URL" `
  --set-secrets="DATABASE_URL=vlegal-database-url:latest,REDIS_URL=vlegal-redis-url:latest,NEO4J_PASSWORD=vlegal-neo4j-password:latest,QDRANT_API_KEY=vlegal-qdrant-api-key:latest,SESSION_SECRET=vlegal-session-secret:latest,MESSAGE_ENCRYPTION_KEY=vlegal-message-key:latest,OIDC_CLIENT_ID=vlegal-oidc-client-id:latest,OIDC_CLIENT_SECRET=vlegal-oidc-client-secret:latest,TAVILY_API_KEY=vlegal-tavily-key:latest"
```

Cloud Run hiện hỗ trợ `nvidia-rtx-pro-6000` tại `asia-southeast1`. Nếu project
chưa có quota, lần deploy GPU đầu có thể yêu cầu cấp quota. Cú pháp đầy đủ của
lệnh nằm tại [`gcloud run deploy`](https://docs.cloud.google.com/sdk/gcloud/reference/run/deploy).

## 8. Cập nhật URL public và Google OAuth

```powershell
$SERVICE_URL = gcloud run services describe $SERVICE `
  --region=$REGION `
  --format="value(status.url)"

gcloud run services update $SERVICE `
  --region=$REGION `
  --update-env-vars="PUBLIC_URL=$SERVICE_URL,FRONTEND_URL=$SERVICE_URL,CORS_ORIGINS=$SERVICE_URL,OIDC_REDIRECT_URI=$SERVICE_URL/api/auth/google/callback,COOKIE_SECURE=true"

Write-Output $SERVICE_URL
```

Trong Google Cloud Console của OAuth client, thêm Authorized redirect URI:

```text
https://<cloud-run-service-host>/api/auth/google/callback
```

Nếu dùng custom domain, cập nhật lại bốn biến URL theo domain đó.

## 9. Kiểm tra deployment

```powershell
curl.exe -fsS "$SERVICE_URL/api/health/live"
curl.exe -fsS "$SERVICE_URL/api/health/ready"
curl.exe -I "$SERVICE_URL/"

gcloud run services logs read $SERVICE `
  --region=$REGION `
  --limit=200
```

`live` phải trả `ok`; `ready` phải trả `ready`. Lần gọi AI đầu tiên sẽ nạp model
từ Cloud Storage vào GPU nên chậm hơn. Sau khi kiểm thử, cân nhắc đặt
`--min-instances=1` để tránh cold start, nhưng GPU sẽ phát sinh chi phí khi giữ
instance nóng.

## 10. Worker và beat

Lệnh trên chỉ deploy ingress container API/frontend. Không deploy Celery worker
hoặc beat vào cùng Cloud Run service:

- Celery worker liên tục nên phù hợp với Cloud Run worker pool, GKE hoặc GCE.
- Tác vụ định kỳ nên chuyển thành Cloud Run Job và gọi bằng Cloud Scheduler.
- Nếu chưa cần refresh corpus nền, API vẫn có thể chạy; kiểm tra hiệu lực trong
  request hiện vẫn hoạt động qua Tavily/Qwen.

## 11. Redeploy và model persistence

Release code mới:

```powershell
$IMAGE_TAG = git rev-parse --short HEAD
$IMAGE = "$REGION-docker.pkg.dev/$PROJECT_ID/$AR_REPO/vlegal-ai:$IMAGE_TAG"

gcloud builds submit --timeout=3600s --tag $IMAGE .
gcloud run jobs update $MIGRATE_JOB --image=$IMAGE --region=$REGION
gcloud run jobs execute $MIGRATE_JOB --region=$REGION --wait
gcloud run services update $SERVICE --image=$IMAGE --region=$REGION
```

Không chạy lại model job khi chỉ đổi code. Checkpoint nằm trong Cloud Storage
bucket nên mọi revision/instance dùng lại; chỉ chạy model job khi đổi
`QWEN_MODEL_REPO` hoặc `QWEN_MODEL_REVISION`.

## 12. Lưu ý trước production

- Cloud Run không chạy nguyên stack Compose; mọi endpoint phụ thuộc phải sẵn sàng.
- Không đưa `.env.production` hoặc secret vào image/source.
- Giữ `max-instances=1` cho tới khi kiểm thử giới hạn Cloud SQL và chi phí GPU.
- Bucket model chỉ cấp quyền cho service account; không public bucket.
- Cloud Storage FUSE không hoàn toàn POSIX và đọc model sẽ chậm hơn local SSD.
- Nếu cần latency ổn định hoặc chạy đủ Compose ít thay đổi, GCE với Persistent
  Disk vẫn đơn giản và thường kinh tế hơn Cloud Run GPU cho workload này.
