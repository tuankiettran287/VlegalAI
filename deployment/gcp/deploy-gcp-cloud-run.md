# Deploy VLegalAI lên Google Cloud

Kiến trúc triển khai không cần GPU hoặc volume chứa model embedding:

| Image | Tài nguyên | Vai trò |
| --- | --- | --- |
| `vlegal-app` | Cloud Run Service, Worker Pool và Job | React SPA, FastAPI, Celery worker/beat, migration, reindex và Vertex AI embeddings |

PostgreSQL/pgvector nên chạy trên Cloud SQL; Neo4j chạy trên Aura, Compute
Engine hoặc GKE. Embedding dùng `gemini-embedding-001` qua Vertex AI với service
identity của Cloud Run.

## 1. Biến triển khai

```powershell
cd F:\VlegalAI

$PROJECT_ID = "your-gcp-project-id"
$REGION = "asia-southeast1"
$EMBEDDING_LOCATION = "global"
$AR_REPO = "vlegal"
$TAG = git rev-parse --short HEAD
$RUN_SA_NAME = "vlegal-run"
$RUN_SA = "$RUN_SA_NAME@$PROJECT_ID.iam.gserviceaccount.com"
$CORPUS_BUCKET = "$PROJECT_ID-vlegal-corpus"
$NEO4J_URI = "neo4j+s://your-neo4j-host:7687"

gcloud auth login
gcloud config set project $PROJECT_ID
```

## 2. Bootstrap project

```powershell
gcloud services enable `
  run.googleapis.com `
  artifactregistry.googleapis.com `
  secretmanager.googleapis.com `
  storage.googleapis.com `
  aiplatform.googleapis.com `
  compute.googleapis.com `
  sqladmin.googleapis.com `
  servicenetworking.googleapis.com

gcloud artifacts repositories create $AR_REPO `
  --repository-format=docker `
  --location=$REGION

gcloud iam service-accounts create $RUN_SA_NAME `
  --display-name="VLegalAI Cloud Run runtime"

gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="serviceAccount:$RUN_SA" `
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID `
  --member="serviceAccount:$RUN_SA" `
  --role="roles/aiplatform.user"

gcloud storage buckets create "gs://$CORPUS_BUCKET" `
  --location=$REGION `
  --uniform-bucket-level-access

gcloud storage buckets add-iam-policy-binding "gs://$CORPUS_BUCKET" `
  --member="serviceAccount:$RUN_SA" `
  --role="roles/storage.objectViewer"

gcloud storage rsync ".\data\legal-documents" "gs://$CORPUS_BUCKET" --recursive
```

## 3. Secret Manager

Tạo các secret mà `deployment/gcp/scripts/deploy.ps1` tham chiếu:

- `vlegal-database-url`
- `vlegal-neo4j-password`
- `vlegal-gemini-api-key`
- `vlegal-session-secret`
- `vlegal-message-key`
- `vlegal-oidc-client-id`
- `vlegal-oidc-client-secret`
- `vlegal-tavily-key`

Ví dụ:

```powershell
"postgresql+asyncpg://vlegal:<password>@<host>:5432/vlegal" |
  gcloud secrets create vlegal-database-url --data-file=-
```

Nếu secret đã tồn tại, thêm version mới bằng `gcloud secrets versions add`.

## 4. Build và push image

```powershell
.\deployment\gcp\scripts\build-images.ps1 `
  -ProjectId $PROJECT_ID `
  -Region $REGION `
  -Repository $AR_REPO `
  -Tag $TAG `
  -Push
```

`docker/app.Dockerfile` tạo một image bất biến cho web, jobs và worker pools.
Cloud Run cấu hình command/args riêng cho migration, reindex và Celery.

## 5. Deploy và reindex

```powershell
.\deployment\gcp\scripts\deploy.ps1 `
  -ProjectId $PROJECT_ID `
  -Region $REGION `
  -EmbeddingLocation $EMBEDDING_LOCATION `
  -Repository $AR_REPO `
  -Tag $TAG `
  -RunServiceAccount $RUN_SA `
  -CorpusBucket $CORPUS_BUCKET `
  -Neo4jUri $NEO4J_URI `
  -Component all `
  -ExecuteMigrate
```

Script thực hiện theo thứ tự: migration, cập nhật reindex job, web service hợp
nhất, worker và beat. Thêm `-ExecuteReindex` khi cần chạy lại toàn bộ reindex.
Reindex tạo vector bằng Vertex AI với:

```dotenv
EMBEDDING_MODEL=gemini-embedding-001
EMBEDDING_LOCATION=global
EMBEDDING_MAX_CONCURRENCY=8
POSTGRES_VECTOR_SIZE=1024
```

Corpus được gửi với task type `RETRIEVAL_DOCUMENT`; query runtime dùng
`RETRIEVAL_QUERY`. Backend chuẩn hoá vector 1024 chiều trước khi lưu/tìm kiếm.
Semantic cache dùng `SEMANTIC_SIMILARITY` vì nó so sánh query với query.

## 6. OAuth và kiểm tra

Trong Google Cloud Console, tạo OAuth client loại **Web application**. Thêm URL
service Cloud Run vào Authorized JavaScript origins và:

```text
https://<service-run-app>/api/auth/google/callback
```

vào Authorized redirect URIs.

Kiểm tra:

```powershell
curl.exe https://<service-run-app>/api/health/live
curl.exe https://<service-run-app>/api/health/ready
```

`/api/health/ready` kiểm tra database, cấu hình Vertex AI/Gemini và dịch vụ kiểm
tra hiệu lực pháp luật bắt buộc.

## 7. Tạo lại embedding

Sau mọi thay đổi model embedding hoặc task type, chạy:

```powershell
.\deployment\gcp\scripts\deploy.ps1 `
  -ProjectId $PROJECT_ID `
  -Region $REGION `
  -EmbeddingLocation $EMBEDDING_LOCATION `
  -Repository $AR_REPO `
  -Tag $TAG `
  -RunServiceAccount $RUN_SA `
  -CorpusBucket $CORPUS_BUCKET `
  -Neo4jUri $NEO4J_URI `
  -Component reindex `
  -ExecuteReindex
```

Migration `20260727_0012` xoá vector của provider cũ vì hai model embedding không
chia sẻ cùng không gian vector. Job reindex phải hoàn tất trước khi API phục vụ
truy hồi vector.

## 8. CI/CD

Để tự động test, build image hợp nhất và deploy khi push vào nhánh `deploy/unified-cloud-run`, xem
[CI/CD với GitHub Actions và Workload Identity Federation](cicd-gcp.md).
