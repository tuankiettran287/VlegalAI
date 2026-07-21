# Deploy VLegal AI bằng Docker

Production chạy trên một máy Linux/VPS bằng `compose.production.yml`. Caddy nhận
traffic ở cổng 80/443 và tự cấp HTTPS; chỉ Caddy được public. API, worker, beat,
PostgreSQL, Redis, Neo4j và Qdrant giao tiếp trong mạng Docker. Dữ liệu được giữ
trong named volumes. Service `model-init` tải checkpoint Qwen từ Hugging Face vào
volume `qwen_model`; API và worker mount volume này ở chế độ read-only.

## 1. Yêu cầu máy chủ

- Linux x86_64, Docker Engine và Docker Compose v2.
- Domain đã có bản ghi A/AAAA trỏ về IP máy chủ.
- Firewall mở TCP 80/443 và UDP 443; SSH chỉ mở cho IP quản trị.
- Đủ RAM/VRAM và dung lượng đĩa cho Qwen3-14B cùng các data store.
- Không cài PostgreSQL, Redis, Neo4j hoặc Qdrant trực tiếp trên host.

Tạo thư mục triển khai:

```bash
sudo install -d -o "$USER" -g "$USER" /opt/vlegal
cd /opt/vlegal
```

## 2. Chuẩn bị cấu hình

Khi deploy thủ công từ source:

```bash
git clone <repository-url> /opt/vlegal
cd /opt/vlegal
cp .env.production.example .env.production
chmod 600 .env.production
```

Tạo secret URL-safe. Mật khẩu PostgreSQL và Redis dùng chuỗi hex để có thể đưa
thẳng vào connection URL:

```bash
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
openssl rand -base64 32 | tr '+/' '-_' | tr -d '=\n'
```

Điền `.env.production`, tối thiểu:

- `DOMAIN`, `ACME_EMAIL`.
- `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `NEO4J_PASSWORD`, `QDRANT_API_KEY`.
- `SESSION_SECRET`, `MESSAGE_ENCRYPTION_KEY`.
- `OIDC_CLIENT_ID`, `OIDC_CLIENT_SECRET`, `TAVILY_API_KEY`.
- `QWEN_MODEL_REPO`, `QWEN_MODEL_REVISION`; thêm `HF_TOKEN` nếu repository model
  yêu cầu xác thực.
- `LEGAL_DATA_HOST_PATH` là đường dẫn tuyệt đối.

Không cần tải model lên host. Khi deploy, `model-init` tải hoặc tiếp tục phần đang
dở, kiểm tra đủ config/tokenizer/trọng số rồi mới cho API và worker khởi động.
Checkpoint đã hoàn tất được giữ trong named volume nên các lần deploy sau chỉ
kiểm tra và dùng lại.

Trong Google Cloud Console, Authorized redirect URI phải là:

```text
https://<DOMAIN>/api/auth/google/callback
```

Không commit `.env.production`; file này đã được `.gitignore`.

## 3. Deploy thủ công

Script deploy sẽ validate Compose, build image, đợi data services healthy, tải
và kiểm tra model, chạy Alembic migration một lần, rồi mới cập nhật
API/worker/beat/Caddy:

```bash
chmod +x scripts/deploy-docker.sh
./scripts/deploy-docker.sh
```

Kiểm tra:

```bash
docker compose --project-name vlegal --env-file .env.production \
  -f compose.production.yml ps
docker compose --project-name vlegal --env-file .env.production \
  -f compose.production.yml logs --tail=200 api caddy
curl -fsS "https://<DOMAIN>/api/health/live"
curl -fsS "https://<DOMAIN>/api/health/ready"
```

`live` xác nhận process API đang chạy. `ready` chỉ trả thành công khi PostgreSQL
và checkpoint Qwen đều sẵn sàng.

## 4. Deploy tự động bằng GitHub Actions

Workflow `.github/workflows/deploy-docker.yml`:

1. Validate `compose.production.yml`.
2. Build một image và push hai tag lên GHCR: Git SHA bất biến và `latest`.
3. Nếu có cấu hình server, copy bundle deploy qua SSH.
4. Pull đúng image Git SHA, chạy migration và cập nhật Compose stack.

Khai báo repository/environment secrets:

| Secret | Giá trị |
| --- | --- |
| `DEPLOY_HOST` | IP hoặc hostname của Docker host |
| `DEPLOY_USER` | User SSH có quyền chạy Docker |
| `DEPLOY_PORT` | Cổng SSH, mặc định `22` |
| `DEPLOY_PATH` | Thư mục deploy, mặc định `/opt/vlegal` |
| `DEPLOY_SSH_KEY` | Private key của deploy user |
| `DEPLOY_KNOWN_HOSTS` | Dòng host key đã kiểm chứng của server |

Nếu repo/GHCR package là private, đăng nhập GHCR một lần trên server bằng token
chỉ có quyền `read:packages`:

```bash
echo "<GHCR-read-token>" | docker login ghcr.io -u "<github-user>" --password-stdin
```

Đặt `.env.production` và legal data sẵn trong `DEPLOY_PATH` trước lần workflow
đầu tiên. Model sẽ được Docker tải trong lần deploy đó. Nếu chưa có `DEPLOY_HOST`,
workflow chỉ build/push image và bỏ qua bước cập nhật server.

## 5. Vận hành

Xem log:

```bash
docker compose --project-name vlegal --env-file .env.production \
  -f compose.production.yml logs -f --tail=200 api worker beat
```

Backup PostgreSQL:

```bash
docker compose --project-name vlegal --env-file .env.production \
  -f compose.production.yml exec -T postgres \
  sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' \
  > "vlegal-$(date +%F-%H%M).dump"
```

Trước mỗi thay đổi schema hoặc nâng phiên bản data store, backup PostgreSQL cùng
các volume Neo4j/Qdrant. Không dùng `docker compose down -v` trên production vì
tham số `-v` xóa toàn bộ named volumes.

Rollback application bằng cách chọn Git SHA image đã chạy tốt:

```bash
VLEGAL_IMAGE=ghcr.io/<owner>/<repo>:<good-sha> PULL_IMAGE=1 \
  ./scripts/deploy-docker.sh
```

Migration phải tương thích ngược với image cũ nếu muốn rollback code an toàn.
Stack một host không có high availability; để chịu lỗi máy chủ cần thêm backup
off-host và chuyển các data store sang cụm/managed service độc lập.
