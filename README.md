# VLegal AI

Nền tảng trợ lý pháp lý Việt Nam gồm hỏi đáp có căn cứ, lịch sử chat, tạo/review/so
sánh hợp đồng bằng Qwen3, chuẩn bị gói ký và nghiên cứu bài viết trên internet.

Người dùng có thể hỏi đáp ngay mà không đăng nhập. Khi đó hội thoại chỉ nằm trong
`sessionStorage` của tab trình duyệt và không được ghi vào PostgreSQL. Đăng nhập
bằng tài khoản Google (Gmail hoặc Google Workspace) sẽ mở lịch sử lâu dài, CRUD
tài liệu và các công cụ hợp đồng.

## Cách hệ thống trả lời

Người dùng không phải chọn RAG, GraphRAG hay từng luật áp dụng. Backend luôn tìm
trên toàn bộ kho luật bằng Hybrid GraphRAG, sau đó thực hiện tuần tự:

1. Mã hoá câu hỏi bằng BGE-M3, lấy các chunk gần nghĩa bằng `pgvector` trong PostgreSQL và mở rộng quan hệ trên Neo4j.
2. Dùng Tavily đối chiếu số hiệu trên các nguồn chính thức được cho phép.
3. Dùng Qwen3 phân loại còn hiệu lực, sửa đổi, hết hiệu lực hoặc bị thay thế.
4. Nếu có bản mới, tải nguồn chính thức, tách Điều/Khoản thành chunk, upsert
   PostgreSQL/pgvector, dựng node/edge Neo4j và truy xuất lại.
5. Chỉ sau đó Qwen3 mới sinh kết quả có trích dẫn `[S1]`, `[S2]`.

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
- `app/worker.py`: Celery refresh toàn bộ kho luật theo lịch.
- `migrations/`: Alembic PostgreSQL migrations.
- `compose.production.yml`: stack production chạy hoàn toàn bằng Docker Compose.
- `Caddyfile`: reverse proxy, HTTPS tự động và security headers.

Nội dung hội thoại, tài liệu hợp đồng, feedback và văn bản trong gói ký được mã
hóa AES-256-GCM trước khi lưu PostgreSQL. PostgreSQL cũng lưu rate limit, cung
cấp distributed advisory lock và làm Celery broker/result backend. Dữ liệu
PostgreSQL, Neo4j, Caddy và chỉ mục pháp lý được lưu trong Docker volumes.

Sau mỗi lượt hỏi đáp đã đăng nhập, Qwen tạo một bản tóm tắt hội thoại lũy tiến.
Summary được mã hóa trước khi lưu; BGE-M3 đồng thời tạo embedding chuẩn hóa 1024
chiều và lưu vào `conversation_summary.embedding` trên pgvector. Lượt chat sau
dùng summary làm bộ nhớ dài hạn và các message gần nhất làm ngữ cảnh ngắn hạn.

Các câu hỏi pháp lý công khai, không có lịch sử phiên hoặc dấu hiệu dữ liệu cá
nhân, được đưa vào semantic answer cache dùng chung. Trước khi tái sử dụng câu
trả lời, hệ thống tìm tương đồng bằng pgvector rồi kiểm tra lại trạng thái và
fingerprint nguồn luật. Query trùng chuẩn hóa được trả trực tiếp; query chỉ tương
tự dùng cache làm bản nháp nhưng vẫn retrieval và sinh câu trả lời đã điều chỉnh.
Câu hỏi có ngữ cảnh riêng luôn sinh câu trả lời mới.

## Cấu hình

Cho môi trường local, sao chép `.env.example` thành `.env`. Production dùng
`.env.production.example` làm mẫu và lưu secret trong `.env.production`. Các biến
bắt buộc cho luồng production:

- `DATABASE_URL`
- `SESSION_SECRET`, `MESSAGE_ENCRYPTION_KEY`
- `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`
- `QWEN_MODEL_PATH`, `QWEN_DEVICE`, `QWEN_DTYPE`, `TAVILY_API_KEY`
- `EMBEDDING_MODEL_PATH`, `EMBEDDING_DEVICE`, `EMBEDDING_BATCH_SIZE`
- `NEO4J_*`, `POSTGRES_VECTOR_SIZE`

`RETRIEVER_BACKEND`, provider và API key chỉ tồn tại ở backend; frontend không
có màn hình cấu hình kỹ thuật hoặc bộ chọn luật.

Qwen3 chạy hoàn toàn trong tiến trình backend bằng checkpoint ở
`QWEN_MODEL_PATH`; không dùng DashScope/OpenAI-compatible API và không gửi prompt
ra dịch vụ model bên ngoài. Service `model-init` tự tải `QWEN_MODEL_REPO` từ
Hugging Face vào named volume `qwen_model`; API và worker chỉ khởi động sau khi
checkpoint đã đầy đủ. Volume được giữ qua các lần rebuild/restart nên model không
bị tải lại. Mỗi API/worker process chỉ nạp một bản model và mặc định xử lý một
lượt sinh tại một thời điểm để tránh nhân bản RAM/VRAM.

BGE-M3 cũng chạy local từ `EMBEDDING_MODEL_PATH`. Mỗi chunk và mỗi câu hỏi đều
được mã hoá bằng cùng checkpoint thành vector chuẩn hoá 1024 chiều; nội dung pháp
lý không được gửi tới embedding API bên ngoài. `model-init` tải checkpoint vào
volume `embedding_model` riêng. Chỉ mục hash 384/1536 chiều cũ không tương thích
và phải được tạo lại sau migration.

Trong Google Cloud Console, tạo OAuth client loại **Web application**, thêm origin
của frontend và đăng ký chính xác redirect URI
`<frontend-url>/api/auth/google/callback`. `frontend-url` có thể là URL mặc định
`*.run.app`, không bắt buộc có domain riêng. `OIDC_ISSUER` luôn là
`https://accounts.google.com`.

Guest chat được giới hạn phân tán qua PostgreSQL bằng
`GUEST_CHAT_REQUESTS_PER_MINUTE` và `GUEST_CHAT_REQUESTS_PER_HOUR` để hạn chế
lạm dụng Qwen/Tavily khi API chạy nhiều replica.

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

Thư mục `docker/` có Dockerfile riêng cho `api`, `frontend`, `worker`, `beat`,
`migrate`, `model-init` và `reindex`; Compose build thành bảy image độc lập. PostgreSQL dùng
image có extension `pgvector`, lưu dữ liệu ứng dụng, rate limit, lock và hàng đợi
Celery; Neo4j lưu graph.
Migration phải thành công trước khi API và worker khởi động.

Chạy local toàn bộ stack, gồm cả bước tải model:

```bash
cp .env.example .env
docker compose up --build
```

Tạo lại toàn bộ embedding từ corpus hiện có và đồng bộ Neo4j/pgvector:

```bash
docker compose run --rm model-init
docker compose run --rm migrate
docker compose --profile jobs run --rm reindex --reset-postgres --reset-neo4j
```

Lần đầu cần đủ dung lượng đĩa và thời gian tải Qwen3-14B. Theo dõi riêng bằng
`docker compose logs -f model-init`; các lần sau checkpoint được dùng lại từ
Docker volume.

Xem [hướng dẫn deploy Docker](deploy.md) và workflow
[deploy-docker.yml](.github/workflows/deploy-docker.yml).

Nếu triển khai lên Google Cloud Run, xem [hướng dẫn Cloud Run](deploy-gcp-cloud-run.md).
API/frontend là hai service riêng dùng URL `run.app`; worker/beat là Worker Pool,
model/migration là Job. Model dùng Cloud Storage volume, PostgreSQL chuyển sang
Cloud SQL và Neo4j chạy trên GCE/GKE hoặc Neo4j Aura.

> VLegal AI hỗ trợ nghiên cứu và nghiệp vụ, không thay thế ý kiến của luật sư
> đối với vụ việc hoặc giao dịch cụ thể.
