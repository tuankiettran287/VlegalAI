# Cloud Shell: deploy API bằng Buildpacks và Secret Manager

Luồng này chỉ dành cho `vlegal-api`. Frontend tiếp tục dùng image Nginx riêng.
Backend được build từ source bằng Google Buildpacks với `Procfile` và
`.python-version`; không cần thêm Dockerfile backend.

Script truyền `GOOGLE_PYTHON_VERSION=3.13.x` và chủ động gỡ build variable
`GOOGLE_ENTRYPOINT` cũ để Buildpacks đọc đủ các process trong `Procfile`
(`web`, `migrate`, `reindex`). Đây là lớp bảo vệ cho lỗi đã thấy trong log:
Cloud Build từng tự chọn Python 3.14 hoặc bỏ qua các process phụ.

Python 3.13 được dùng đồng nhất với backend Dockerfile và GitHub Actions. Builder
Cloud Run hiện tại không còn cung cấp Python 3.12, nên ép `3.12.x` sẽ dừng ở bước
resolve runtime trước khi cài dependency.

## Một lệnh cho lần đầu

Trong Google Cloud Shell:

```bash
cd ~/VlegalAI
git pull --ff-only origin master

chmod +x scripts/gcp/setup-secret-manager.sh
chmod +x scripts/gcp/deploy-api-buildpacks.sh

./scripts/gcp/deploy-api-buildpacks.sh \
  --project idyllic-anvil-452006-k0 \
  --region asia-southeast1 \
  --frontend-url https://vlegal-frontend-201653369723.asia-southeast1.run.app \
  --neo4j-uri neo4j+s://YOUR_INSTANCE.databases.neo4j.io \
  --neo4j-user YOUR_NEO4J_USER \
  --neo4j-database YOUR_NEO4J_DATABASE
```

Script hỏi lần lượt tám giá trị và ẩn ký tự nhập:

- `DATABASE_URL`
- `NEO4J_PASSWORD`
- `GEMINI_API_KEY`
- `TAVILY_API_KEY`
- `OIDC_CLIENT_ID`
- `OIDC_CLIENT_SECRET`
- `SESSION_SECRET`
- `MESSAGE_ENCRYPTION_KEY`

Không giá trị nào được đưa vào command line, shell history hoặc file trong repo.
Nếu secret đã có version đang bật, nhấn Enter để giữ nguyên. Nếu hai khóa
session/encryption chưa tồn tại, nhấn Enter để script sinh giá trị phù hợp.

Sau khi Secret Manager sẵn sàng, cùng script sẽ deploy API và kiểm tra:

```text
/api/health/live
/api/health/ready
```

## Những lần deploy sau

Không cần nhập lại secret:

```bash
./scripts/gcp/deploy-api-buildpacks.sh \
  --project idyllic-anvil-452006-k0 \
  --region asia-southeast1 \
  --frontend-url https://vlegal-frontend-201653369723.asia-southeast1.run.app \
  --neo4j-uri neo4j+s://YOUR_INSTANCE.databases.neo4j.io \
  --neo4j-user YOUR_NEO4J_USER \
  --neo4j-database YOUR_NEO4J_DATABASE \
  --skip-secret-setup
```

Script dùng `--update-env-vars` và `--update-secrets`, vì vậy không xóa những cấu
hình Cloud Run khác. Không dùng lại lệnh cũ chứa toàn bộ credential trong
`--set-env-vars`.

Các build variable cũng được cập nhật bằng `--update-build-env-vars`, không ghi
đè những build variable không thuộc script.

Nếu service cũ đang giữ credential dưới dạng biến môi trường thường, script tự
nhận diện và gỡ đúng các biến đó trong một revision không nhận traffic trước khi
bind Secret Manager. Bản source mới cũng được deploy không traffic, kiểm tra
`live`/`ready` qua URL có tag, rồi mới chuyển 100% traffic sang revision mới.

Production giữ `GEMINI_USE_ADC=true` cho Gemini generation trên Vertex AI.
Embedding dùng `EMBEDDING_PROVIDER=gemini-api` và lấy `GEMINI_API_KEY` từ Secret
Manager. Batch 20 văn bản giúp tránh quota Vertex AI 5 request/phút nhưng vẫn giữ
nguyên model `gemini-embedding-001` và vector 1024 chiều.

## Chạy reindex sau khi deploy API

Script dưới đây tự lấy image từ revision API mới nhất, cấu hình job 4 CPU/8 GiB,
chạy migration GraphRAG reset/reindex và chỉ refresh API sau khi job thành công:

```bash
chmod +x scripts/gcp/run-reindex-buildpacks.sh

./scripts/gcp/run-reindex-buildpacks.sh \
  --project idyllic-anvil-452006-k0 \
  --region asia-southeast1 \
  --neo4j-uri neo4j+s://YOUR_INSTANCE.databases.neo4j.io \
  --neo4j-user neo4j \
  --neo4j-database neo4j
```

Không cần nhập lại API key; job bind version `latest` của
`vlegal-gemini-api-key` từ Secret Manager.

## Xem lỗi build

Nếu Buildpacks thất bại, script in sẵn lệnh đọc build gần nhất. Có thể tự lấy:

```bash
BUILD_ID="$(
  gcloud builds list \
    --project=idyllic-anvil-452006-k0 \
    --region=asia-southeast1 \
    --limit=1 \
    --format='value(id)'
)"

gcloud beta builds log "$BUILD_ID" \
  --project=idyllic-anvil-452006-k0 \
  --region=asia-southeast1
```

Build thất bại không thay revision đang nhận traffic.

## Rollback

Liệt kê revision:

```bash
gcloud run revisions list \
  --service=vlegal-api \
  --project=idyllic-anvil-452006-k0 \
  --region=asia-southeast1
```

Chuyển 100% traffic về revision ổn định:

```bash
gcloud run services update-traffic vlegal-api \
  --project=idyllic-anvil-452006-k0 \
  --region=asia-southeast1 \
  --to-revisions=REVISION_NAME=100
```
