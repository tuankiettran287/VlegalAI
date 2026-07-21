# Qwen offline checkpoint

Docker Compose tự tải `QWEN_MODEL_REPO` bằng service `model-init` và lưu checkpoint
trong named volume `qwen_model`. API/worker mount volume đó read-only tại
`/models/qwen3` và chỉ đọc file cục bộ (`local_files_only=True`). Không cần đặt
trọng số model trong thư mục source này.

Mặc định dùng `Qwen/Qwen3-14B` ở revision `main`. Có thể đổi bằng
`QWEN_MODEL_REPO`, `QWEN_MODEL_REVISION` và đặt `HF_TOKEN` cho repository
private/gated. Theo dõi quá trình tải bằng:

```bash
docker compose logs -f model-init
```

Chọn thiết bị bằng `QWEN_DEVICE=auto|cuda|cpu|mps` và kiểu số bằng
`QWEN_DTYPE=auto|bfloat16|float16|float32`. Không đặt `float16` cho CPU.
