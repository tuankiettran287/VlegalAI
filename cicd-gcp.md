# CI/CD VLegalAI với GitHub Actions và Google Cloud

Workflow [`.github/workflows/deploy-gcp.yml`](.github/workflows/deploy-gcp.yml)
chạy CI khi có pull request vào `master`; khi push vào `master` hoặc chạy thủ
công, workflow tiếp tục chạy toàn bộ CD production:

1. Kiểm tra dependency Python, compile source, Alembic chỉ có một head, cú pháp
   Bash/PowerShell và hai Docker Compose manifest.
2. Chạy toàn bộ test backend.
3. Chạy TypeScript check và production build cho frontend.
4. Với pull request, build thử container hợp nhất nhưng không push và không truy cập
   GitHub environment `production`.
5. Đăng nhập Google Cloud bằng GitHub OIDC/Workload Identity Federation.
6. Build và push image `vlegal-app` bằng tag Git commit SHA bất biến.
7. Chạy Cloud Run migration job và chờ hoàn tất.
8. Deploy service hợp nhất `vlegal-unified`, Celery worker/beat và cập nhật reindex job.
9. Gọi cả `/api/health/live` và `/api/health/ready` qua service hợp nhất.
10. Chỉ sau khi hai health check thành công mới chuyển tag `latest` sang image
    vừa được xác minh.

Reindex toàn bộ vector không chạy ở mỗi lần push. Nó reset chỉ mục và gọi Vertex
AI cho toàn bộ corpus, vì vậy chỉ được bật khi chạy workflow thủ công với input
`run_reindex=true`.

## 1. Chuẩn bị GCP và Workload Identity Federation

Cần Google Cloud CLI đã đăng nhập bằng tài khoản có quyền tạo service account,
IAM binding, Workload Identity Pool, Artifact Registry và Cloud Storage bucket.

Script đã mặc định khóa vào repository `tuankiettran287/VlegalAI` với repository
ID `1299341579` và owner ID `148296828`. Chạy bootstrap một lần:

```powershell
.\scripts\gcp\setup-github-cicd.ps1 `
  -ProjectId "YOUR_PROJECT_ID" `
  -Region "asia-southeast1"
```

Nếu chạy từ một fork, truyền lại `-GitHubRepositoryId`,
`-GitHubRepositoryOwnerId` và repository variables tương ứng.
Script thực hiện idempotent:

- bật các Google Cloud API cần thiết;
- tạo Artifact Registry repository và corpus bucket nếu chưa có;
- tạo deployment/runtime service account nếu chưa có;
- cấp quyền Cloud Run, Artifact Registry, Vertex AI, Cloud SQL và Secret Manager;
- tạo GitHub OIDC provider;
- chỉ cho phép đúng numeric repository ID, owner ID và nhánh `master`;
- in ra toàn bộ giá trị cần thêm vào GitHub.

Sau khi tạo mới Workload Identity Pool/Provider, có thể cần chờ vài phút để IAM
đồng bộ trước lần chạy workflow đầu tiên.

## 2. Cấu hình GitHub environment

Trong GitHub repository, mở **Settings → Environments**, tạo environment
`production`.

Thêm các environment variables do script bootstrap in ra:

| Variable | Ví dụ |
| --- | --- |
| `GCP_PROJECT_ID` | `your-project-id` |
| `GCP_REGION` | `asia-southeast1` |
| `GCP_EMBEDDING_LOCATION` | `global` |
| `EMBEDDING_VERTEX_LOCATIONS` | `asia-east1|asia-east2|...|us-west4` (bỏ trống để dùng pool mặc định) |
| `EMBEDDING_VERTEX_REQUESTS_PER_MINUTE` | `4.5` |
| `GCP_REPOSITORY` | `vlegal` |
| `GCP_RUN_SERVICE` | `vlegal-unified` |
| `GCP_RUN_SERVICE_ACCOUNT` | `vlegal-run@PROJECT_ID.iam.gserviceaccount.com` |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | `vlegal-github-deploy@PROJECT_ID.iam.gserviceaccount.com` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/github-actions/providers/vlegal` |
| `GCP_CORPUS_BUCKET` | `PROJECT_ID-vlegal-corpus` |
| `GCP_CLOUD_SQL_INSTANCE` | `PROJECT_ID:asia-east2:PROJECT_ID-instance` |
| `NEO4J_USER` | username được Aura cấp (có thể bỏ trống nếu trùng instance ID trong URI) |
| `NEO4J_DATABASE` | database được Aura cấp (có thể bỏ trống nếu trùng instance ID trong URI) |

Thêm environment secret:

| Secret | Nội dung |
| --- | --- |
| `NEO4J_URI` | Ví dụ `neo4j+s://your-neo4j-host:7687` |

Không lưu service-account JSON key trong GitHub.

Các secret ứng dụng sau vẫn phải tồn tại trong Google Secret Manager:

- `vlegal-database-url`
- `vlegal-neo4j-password`
- `vlegal-gemini-api-key`
- `vlegal-session-secret`
- `vlegal-message-key`
- `vlegal-oidc-client-id`
- `vlegal-oidc-client-secret`
- `vlegal-tavily-key`

## 3. Deploy tự động

Commit các file CI/CD và push lên `master`:

```powershell
git add .
git commit -m "Add GCP CI/CD"
git push origin master
```

Theo dõi workflow:

```powershell
gh run watch
```

Workflow dùng commit SHA làm image tag để mỗi Cloud Run revision trỏ tới một
artifact bất biến. Tag `latest` vẫn trỏ tới release khỏe gần nhất nếu deployment
mới lỗi. Các deployment được xếp hàng bằng concurrency group
`vlegal-production`; CI của pull request không chiếm hàng đợi production và một
deployment đang chạy sẽ không bị commit mới hủy giữa chừng.

## 4. Chạy reindex thủ công

Sau khi thay model embedding, task type, vector dimension hoặc corpus:

```powershell
gh workflow run deploy-gcp.yml `
  --ref master `
  -f run_reindex=true
```

Lệnh này vẫn chạy test/build/deploy bình thường, sau đó thực thi và chờ reindex
job hoàn tất.

## 5. Lưu ý vận hành

- Migration chạy ở mỗi deployment và phải hoàn tất trước khi revision mới được
  cập nhật.
- Worker và beat hiện được deploy với `--instances=1`, vì vậy phát sinh chi phí
  liên tục thay vì scale về zero như API/frontend.
- Nếu GitHub environment `production` có required reviewers, deployment sẽ chờ
  phê duyệt và không còn hoàn toàn tự động.
- OIDC provider chỉ chấp nhận nhánh `master`; chạy workflow từ nhánh khác sẽ bị GCP
  từ chối xác thực.
