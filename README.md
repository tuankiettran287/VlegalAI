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

1. Lấy các chunk liên quan từ Qdrant và mở rộng quan hệ trên Neo4j.
2. Dùng Tavily đối chiếu số hiệu trên các nguồn chính thức được cho phép.
3. Dùng Qwen3 phân loại còn hiệu lực, sửa đổi, hết hiệu lực hoặc bị thay thế.
4. Nếu có bản mới, tải nguồn chính thức, tách Điều/Khoản thành chunk, upsert
   PostgreSQL + Qdrant, dựng node/edge Neo4j và truy xuất lại.
5. Chỉ sau đó Qwen3 mới sinh kết quả có trích dẫn `[S1]`, `[S2]`.

Kết quả API kèm `verification` để frontend hiển thị thời điểm kiểm tra, trạng
thái từng văn bản, URL chính thức và việc chỉ mục có vừa được cập nhật hay không.

## Kiến trúc

- `frontend/`: React + TypeScript + Vite, responsive, Google login, guest chat, lịch sử và CRUD.
- `app/main.py`: FastAPI app factory/lifespan, middleware và static SPA.
- `app/api.py`: chat, hợp đồng AI, conversation/artifact/article CRUD, chữ ký.
- `app/auth.py`: Google OIDC Authorization Code + PKCE và session cookie HttpOnly.
- `app/models.py`: SQLAlchemy PostgreSQL models.
- `app/services/freshness.py`: kiểm tra hiệu lực bắt buộc trước kết quả pháp lý.
- `app/services/indexer.py`: tải luật mới, chunk, cập nhật Qdrant và Neo4j.
- `app/worker.py`: Celery refresh toàn bộ kho luật theo lịch.
- `migrations/`: Alembic PostgreSQL migrations.
- `infra/aws/`: ECS Fargate, ALB, RDS PostgreSQL, RDS Proxy, ElastiCache, ECR,
  Secrets Manager, autoscaling và CloudWatch bằng Terraform.

Nội dung hội thoại, tài liệu hợp đồng, feedback và văn bản trong gói ký được mã
hóa AES-256-GCM trước khi lưu PostgreSQL. RDS, Redis và lưu lượng nội bộ production
đều được cấu hình mã hóa.

## Cấu hình

Sao chép `.env.example` thành `.env`. Các biến bắt buộc cho luồng production:

- `DATABASE_URL`, `REDIS_URL`
- `SESSION_SECRET`, `MESSAGE_ENCRYPTION_KEY`
- `OIDC_ISSUER`, `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`
- `QWEN_API_KEY`, `TAVILY_API_KEY`
- `NEO4J_*`, `QDRANT_*`

`RETRIEVER_BACKEND`, provider và API key chỉ tồn tại ở backend; frontend không
có màn hình cấu hình kỹ thuật hoặc bộ chọn luật.

Trong Google Cloud Console, tạo OAuth client loại **Web application**, thêm origin
của frontend và đăng ký chính xác redirect URI
`https://<domain>/api/auth/google/callback`. `OIDC_ISSUER` luôn là
`https://accounts.google.com`.

Guest chat được giới hạn phân tán qua Redis bằng
`GUEST_CHAT_REQUESTS_PER_MINUTE` và `GUEST_CHAT_REQUESTS_PER_HOUR` để hạn chế
lạm dụng Qwen/Tavily khi API chạy nhiều replica.

## Database và API

Migration đầu tiên tạo user/SSO identity, conversation/message, artifact, legal
document/chunk, article, signature packet và feedback. API chính:

- `GET /api/auth/google/login`, `GET /api/auth/google/callback`, `GET /api/auth/me`
- CRUD `/api/conversations` và `/api/artifacts`
- `POST /api/chat` (public; chỉ persist khi có Google session hợp lệ)
- `POST /api/contracts/draft`, `/review`, `/compare`
- CRUD `/api/articles` và `POST /api/articles/web-search`
- `POST /api/signatures/prepare`
- `GET /api/laws` để theo dõi phiên bản và thời điểm kiểm tra

## Container và AWS

`Dockerfile` build frontend rồi đóng gói chung với API. `docker-compose.yml` mô
tả toàn bộ stack phát triển. Production sử dụng `infra/aws`: tối thiểu hai API
task và hai worker, scale ngang đến giới hạn cấu hình; PostgreSQL chạy trên RDS
Multi-AZ qua RDS Proxy. Migration chạy bằng task definition riêng trước khi roll
service, không chạy đồng thời trong mọi replica.

Xem [hướng dẫn AWS](infra/aws/README.md) và workflow
[deploy-aws.yml](.github/workflows/deploy-aws.yml).

> VLegal AI hỗ trợ nghiên cứu và nghiệp vụ, không thay thế ý kiến của luật sư
> đối với vụ việc hoặc giao dịch cụ thể.
