# Evaluation

Mỗi lần benchmark được giữ trong một thư mục riêng để dữ liệu đầu vào, kết quả
truy hồi, câu trả lời, checkpoint chấm điểm và báo cáo không bị tách rời.

## RAGAS Gemini 100

`benchmarks/ragas-gemini-100/` chứa bộ 100 câu hỏi và artifact so sánh các kiến
trúc RAG/GraphRAG dùng `gemini-embedding-001` và `gemini-2.5-flash`.

- `questions_*.jsonl`: dữ liệu đầu vào và câu trả lời tham chiếu.
- `retrieval_*.jsonl`: kết quả truy hồi.
- `answers_*.jsonl`: câu trả lời theo từng kiến trúc.
- `ragas_*`: checkpoint và bảng điểm RAGAS.
- `benchmark_summary.json`, `architecture_comparison.*`: kết quả tổng hợp.
