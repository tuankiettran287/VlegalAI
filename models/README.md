# Qwen offline checkpoint

Đặt toàn bộ checkpoint Qwen3 đã tải sẵn vào thư mục con, mặc định:

```text
models/Qwen3-4B/
  config.json
  generation_config.json
  tokenizer.json
  tokenizer_config.json
  model-*.safetensors
  model.safetensors.index.json
```

Ứng dụng chỉ đọc file cục bộ (`local_files_only=True`) và không tự tải model.
Các file trọng số bị loại khỏi Git và Docker build context. Docker Compose mount
thư mục này read-only tại `/models/qwen3`; có thể đổi nguồn mount bằng biến
`QWEN_MODEL_HOST_PATH`.

Chọn thiết bị bằng `QWEN_DEVICE=auto|cuda|cpu|mps` và kiểu số bằng
`QWEN_DTYPE=auto|bfloat16|float16|float32`. Không đặt `float16` cho CPU.
