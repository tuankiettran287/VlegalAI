# VLegal AI

Nền tảng trợ lý pháp lý Việt Nam gồm hỏi đáp có căn cứ, lịch sử chat, tạo/review/so
sánh hợp đồng bằng Gemini 3.5 Flash, chuẩn bị gói ký và nghiên cứu bài viết trên internet.

Người dùng có thể hỏi đáp ngay mà không đăng nhập. Khi đó hội thoại chỉ nằm trong
`sessionStorage` của tab trình duyệt và không được ghi vào PostgreSQL. Đăng nhập
bằng tài khoản Google (Gmail hoặc Google Workspace) sẽ mở lịch sử lâu dài, CRUD
tài liệu và các công cụ hợp đồng.

## Cách hệ thống trả lời

Người dùng không phải chọn RAG, GraphRAG hay từng luật áp dụng. Backend luôn tìm
trên toàn bộ kho luật bằng Hybrid GraphRAG, sau đó thực hiện tuần tự:

1. Mã hoá câu hỏi bằng Vertex AI `gemini-embedding-001`, lấy các chunk gần nghĩa bằng `pgvector` trong PostgreSQL và mở rộng quan hệ trên Neo4j.
2. Chạy Tavily và Google Search grounding song song, khử trùng lặp rồi chỉ giữ
   kết quả thuộc các nguồn chính thức được cho phép.
3. Dùng Gemini 3.5 Flash phân loại còn hiệu lực, sửa đổi, hết hiệu lực hoặc bị thay thế.
4. Nếu có bản mới, tải nguồn chính thức, tách Điều/Khoản thành chunk, upsert
   PostgreSQL/pgvector, dựng node/edge Neo4j và truy xuất lại.
5. Chỉ sau đó Gemini 3.5 Flash mới sinh kết quả có trích dẫn `[S1]`, `[S2]`.

Nếu văn bản đã hết hiệu lực hoặc bị thay thế, backend tải văn bản thay thế từ URL
chính thức, tách Điều/Khoản thành chunk, tạo embedding bằng Vertex AI, upsert
PostgreSQL/pgvector, tạo node/chunk Neo4j và quan hệ `REPLACES`, rồi truy xuất lại
trước khi sinh câu trả lời.

Kết quả API kèm `verification` để frontend hiển thị thời điểm kiểm tra, trạng
thái từng văn bản, URL chính thức và việc chỉ mục có vừa được cập nhật hay không.

## Kiến trúc

- `frontend/`: ReactJS + TypeScript + Vite, responsive, Google login, guest chat, lịch sử và CRUD.
- `app/main.py`: FastAPI API service, lifespan và middleware.
- `app/api.py`: chat, hợp đồng AI, conversation/artifact/article CRUD, chữ ký.
- `app/auth.py`: Google OIDC Authorization Code + PKCE và session cookie HttpOnly.
- `app/models.py`: SQLAlchemy PostgreSQL models.
- `app/services/freshness.py`: kiểm tra hiệu lực bắt buộc trước kết quả pháp lý.
- `app/services/indexer.py`: tải luật mới, chunk, cập nhật PostgreSQL/pgvector và Neo4j.
- `app/legal_ontology.py`: bản thể học 10 tầng của đồ thị pháp luật (loại nút, quan hệ,
  trọng số truy hồi, từ điển tiền lương/tiền thưởng, chế tài, chủ đề).
- `app/legal_graphrag.py`: bộ dựng đồ thị từ `.docx` và kho truy hồi cục bộ SQLite + FTS5.
- `evaluation/question_bank.json` + `scripts/run_question_bank.py`: bộ 70 câu hỏi phân tầng
  single-hop → multi-hop → multi-abstract và trình chạy đo độ chính xác, độ trễ.
  Chi tiết kiến trúc: [GraphRAG_Documentation.md](GraphRAG_Documentation.md).
- `app/worker.py`: Celery refresh toàn bộ kho luật theo lịch.
- `migrations/`: Alembic PostgreSQL migrations.
- `compose.gcp.yml`: build/tag các image `linux/amd64` cho Google Artifact Registry.
- `scripts/gcp/`: build và deploy Cloud Run Service, Worker Pool và Job.

Nội dung hội thoại, tài liệu hợp đồng, feedback và văn bản trong gói ký được mã
hóa AES-256-GCM trước khi lưu PostgreSQL. PostgreSQL cũng lưu rate limit, cung
cấp distributed advisory lock và làm Celery broker/result backend. Dữ liệu
PostgreSQL được quản lý bên ngoài (ví dụ Cloud SQL); Neo4j, Caddy và chỉ mục pháp
lý được lưu trong Docker volumes.

Sau mỗi lượt hỏi đáp đã đăng nhập, Gemini tạo một bản tóm tắt hội thoại lũy tiến.
Summary được mã hóa trước khi lưu; Gemini Embedding 001 đồng thời tạo embedding chuẩn hóa 1024
chiều và lưu vào `conversation_summary.embedding` trên pgvector. Lượt chat sau
dùng summary làm bộ nhớ dài hạn và các message gần nhất làm ngữ cảnh ngắn hạn.

Các câu hỏi pháp lý công khai, không có lịch sử phiên hoặc dấu hiệu dữ liệu cá
nhân, có thể được đưa vào semantic answer cache tách biệt theo người dùng hoặc
phiên khách. Trước khi tái sử dụng câu trả lời, hệ thống chỉ tìm trong đúng phạm
vi đó bằng pgvector rồi kiểm tra lại trạng thái và fingerprint nguồn luật. Query
trùng chuẩn hóa được trả trực tiếp; query chỉ tương tự dùng cache làm bản nháp
nhưng vẫn retrieval và sinh câu trả lời đã điều chỉnh.
Câu hỏi có ngữ cảnh riêng luôn sinh câu trả lời mới.

## Cấu hình

Cho môi trường local, sao chép `.env.example` thành `.env`. Trên GCP, cấu hình
runtime được truyền bởi `scripts/gcp/deploy.ps1`; secret được đọc từ Secret Manager
và Gemini dùng service identity qua ADC. Các biến bắt buộc cho production:

- `DATABASE_URL`
- `SESSION_SECRET`, `MESSAGE_ENCRYPTION_KEY`
- `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`
- `GEMINI_PROJECT_ID`, `GEMINI_USE_ADC=true`, `GEMINI_MODEL`, `GEMINI_LOCATION`, `TAVILY_API_KEY`
- `EMBEDDING_MODEL`, `EMBEDDING_LOCATION`, `EMBEDDING_MAX_CONCURRENCY`
- `EMBEDDING_VERTEX_LOCATIONS`, `EMBEDDING_VERTEX_REQUESTS_PER_MINUTE`
- `NEO4J_*`, `POSTGRES_VECTOR_SIZE`

`RETRIEVER_BACKEND`, provider và API key chỉ tồn tại ở backend; frontend không
có màn hình cấu hình kỹ thuật hoặc bộ chọn luật.

Gemini 3.5 Flash được gọi qua Vertex AI. Backend đọc Google service-account
credential từ file `env.json` (hoặc `GEMINI_CREDENTIALS_PATH`), lấy OAuth access
token và gửi prompt tới model `gemini-3.5-flash`; credential không được trả về
frontend hay ghi vào log. Service account cần quyền gọi Vertex AI trong project
và Vertex AI API phải được bật. Google Search grounding dùng cùng credential,
không cần thêm Custom Search API key/CX; project cần bật Google Search
Suggestions trong Vertex AI.

Trên Cloud Run, đặt `GEMINI_USE_ADC=true` để dùng service identity; file
`GEMINI_CREDENTIALS_PATH` chỉ cần cho môi trường local không dùng ADC.

Deploy thủ công API từ Cloud Shell bằng Buildpacks và nhập credential kín vào
Secret Manager theo
[`scripts/gcp/CLOUD_SHELL_BUILDPACKS.md`](scripts/gcp/CLOUD_SHELL_BUILDPACKS.md).

`GEMINI_DATA_POLICY=redact` là mặc định: email, số điện thoại, định danh, số tài
khoản và secret phổ biến được che trước khi gửi ra Vertex AI/Tavily/Google Search.
Chỉ đặt `allow` khi tổ chức đã phê duyệt rõ chính sách dữ liệu tương ứng.

Một cấu hình model duy nhất được dùng cho hỏi đáp, kiểm tra hiệu lực, tạo/review/
so sánh hợp đồng, nghiên cứu bài viết, tóm tắt bộ nhớ hội thoại và LLM-judge của
bộ đánh giá. Embedding truy xuất/cache dùng riêng `gemini-embedding-001` qua Vertex AI.

Chức năng Bài viết tìm đồng thời bằng Tavily và Google Search grounding. Các URL
do Google tìm thấy được Tavily Extract bổ sung nội dung khi có thể; frontend hiển
thị provider của từng nguồn và Google Search entry point.

Gemini Embedding 001 chạy qua Vertex AI với cùng service account/ADC của lớp sinh
nội dung. Corpus dùng task type `RETRIEVAL_DOCUMENT`, câu hỏi dùng
`RETRIEVAL_QUERY`; mỗi request đặt `outputDimensionality=1024` và backend chuẩn
hoá lại vector giảm chiều trước khi lưu hoặc tìm kiếm. Khi đổi model embedding,
vector size hoặc `GEMINI_DATA_POLICY`, toàn bộ chỉ mục vector phải được tạo lại.
Với project có quota thấp, `EMBEDDING_VERTEX_LOCATIONS` phân phối cùng model qua
nhiều region; `EMBEDDING_VERTEX_REQUESTS_PER_MINUTE` giới hạn riêng từng region
để tránh HTTP 429.
Semantic cache dùng task type đối xứng `SEMANTIC_SIMILARITY` và chỉ so khớp các
row được tạo bằng đúng model/revision embedding hiện tại.

Trong Google Cloud Console, tạo OAuth client loại **Web application**, thêm origin
của frontend và đăng ký chính xác redirect URI
`<frontend-url>/api/auth/google/callback`. `frontend-url` có thể là URL mặc định
`*.run.app`, không bắt buộc có domain riêng. `OIDC_ISSUER` luôn là
`https://accounts.google.com`.

Guest chat được giới hạn phân tán qua PostgreSQL bằng
`GUEST_CHAT_REQUESTS_PER_MINUTE` và `GUEST_CHAT_REQUESTS_PER_HOUR` để hạn chế
lạm dụng Gemini/Tavily khi API chạy nhiều replica.

### Chạy backend local với Cloud SQL

Backend local kết nối trực tiếp Public IP của Cloud SQL qua TLS. Cấu hình
`DATABASE_URL` trong `.env` bằng host Public IP, port `5432` và
`sslmode=require`. IP Internet của máy chạy backend phải được thêm vào
**Cloud SQL > Connections > Networking > Authorized networks**.

```powershell
.\scripts\run_backend_local.ps1 -Reload
```

Script chạy `alembic upgrade head`, sau đó mở API tại
`http://127.0.0.1:8000`. Không sử dụng Cloud SQL Auth Proxy và không cần chạy
database bằng Docker.

## Database và API

Các migration tạo user/SSO identity, conversation/message, summary embedding,
artifact, legal document/chunk, article, signature packet, feedback và rate
limit PostgreSQL. API chính:

- `GET /api/auth/google/login`, `GET /api/auth/google/callback`, `GET /api/auth/me`
- CRUD `/api/conversations` và `/api/artifacts`
- `POST /api/chat` (public; chỉ persist khi có Google session hợp lệ)
- `POST /api/contracts/draft`, `/review`, `/compare`
- CRUD `/api/articles` và `POST /api/articles/web-search`
- `POST /api/signatures/prepare`
- `GET /api/laws` để theo dõi phiên bản và thời điểm kiểm tra

## Docker

`docker/app.Dockerfile` tạo một image `vlegal-app` chứa React SPA và FastAPI.
Cloud Run web service, Celery worker/beat, migration và reindex dùng chung đúng
image của một commit; Cloud Run ghi đè command theo từng vai trò. Web service
phục vụ frontend và `/api` trực tiếp, không cần Nginx hoặc reverse proxy riêng.
PostgreSQL/pgvector là dịch vụ được quản lý bên ngoài và được kết nối qua
`DATABASE_URL` trong file env; Compose không khởi động database. Neo4j lưu graph.
Migration phải thành công trước khi API và worker khởi động.

Compose tự đọc `.env` và nạp file này vào tất cả process backend. `.env` không
được copy vào image. `env.json` cũng không nằm trong image mà được mount read-only
qua Compose secret tại `/run/secrets/gcp_credentials`; cả text generation và
embedding Vertex AI dùng credential này. Corpus `.docx` và chỉ mục SQLite cục bộ
chỉ được mount vào `reindex` — image duy nhất dựng chỉ mục — đúng như cấu hình
Cloud Run, nơi chỉ job reindex mount corpus bucket.

Chạy local toàn bộ stack (đặt `env.json` ở thư mục gốc trước khi chạy):

```bash
cp .env.example .env
docker compose --env-file .env up --build
```

`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` và `NEO4J_DATABASE` phải trỏ tới
Neo4j được quản lý bên ngoài (ví dụ Neo4j Aura).

Tạo lại toàn bộ embedding từ corpus hiện có và đồng bộ Neo4j/pgvector:

```bash
docker compose --env-file .env run --rm migrate
docker compose --env-file .env --profile jobs run --rm reindex
```

Neo4j được quản lý bên ngoài (ví dụ Neo4j Aura); image production không đóng
gói hoặc khởi động Neo4j/Nginx.

Service account phải có `roles/aiplatform.user` và project phải bật
`aiplatform.googleapis.com`. Reindex sẽ gửi corpus tới Vertex AI để tạo lại toàn
bộ vector.

Xem [hướng dẫn Cloud Run](deploy-gcp-cloud-run.md) để build và triển khai lên GCP.
Frontend/API dùng chung một service `vlegal-unified` với URL `run.app`; worker/beat là
Worker Pool, migration/reindex là Job. PostgreSQL chạy trên Cloud SQL và Neo4j
chạy trên Neo4j Aura.

Để tự động test, build và deploy mỗi khi push vào `master`, xem
[hướng dẫn CI/CD GitHub Actions](cicd-gcp.md). Workflow dùng Workload Identity
Federation, không lưu service-account JSON key trong GitHub.

> VLegal AI hỗ trợ nghiên cứu và nghiệp vụ, không thay thế ý kiến của luật sư
> đối với vụ việc hoặc giao dịch cụ thể.
