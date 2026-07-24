# BGE-M3 offline embedding checkpoint

Docker Compose tải `EMBEDDING_MODEL_REPO` bằng service `model-init` và lưu
checkpoint trong named volume `embedding_model`. API, worker và reindex mount
volume này read-only tại `/models/embedding`; văn bản pháp luật được embedding
cục bộ và không gửi sang dịch vụ embedding bên ngoài.

Mặc định dùng `BAAI/bge-m3` ở revision đã cấu hình bởi
`EMBEDDING_MODEL_REVISION`. Có thể đặt `HF_TOKEN` nếu repository yêu cầu xác
thực. Theo dõi quá trình tải bằng:

```bash
docker compose logs -f model-init
```

Chọn thiết bị bằng `EMBEDDING_DEVICE=auto|cuda|cpu|mps`. Lớp sinh nội dung,
phân loại hiệu lực và tóm tắt dùng Vertex AI Gemini theo các biến
`GEMINI_*`; không còn tải checkpoint Qwen vào container.
