# LaborCare GraphRAG

Chatbot pháp luật lao động dùng GraphRAG theo cấu trúc văn bản pháp luật:

- `VănBản -> Chương -> Mục -> Điều -> Khoản -> Điểm`
- Quan hệ `THUỘC_VỀ`, `HƯỚNG_DẪN`, `DẪN_CHIẾU_ĐẾN`, `SỬA_ĐỔI`, `THAY_THẾ`, `BAN_HÀNH`
- Chunk hỗn hợp: document intro, structure, article, clause, point, sliding-window
- Staging artifact: SQLite/JSONL để parse và sync dữ liệu
- Runtime backend: Neo4j local cho graph + Qdrant Cloud cho vector chunks
- LLM: Groq API

## Tài liệu thiết kế database

- Logical ERD và mapping AS-IS/TO-BE: `docs/design/VLegalAI_ERD.md`
- Physical Database Design cho user/chat: `docs/design/VLegalAI_Physical_Database_Design.md`
- PostgreSQL DDL hash-only user/conversation: `docs/design/sql/V001__runtime_user_privacy.sql`
- Báo cáo có checklist table/field/type/size/default/logical mapping: `BAO_CAO_DANH_GIA_VLEGALAI_RAG_GRAPHRAG_V2_1.docx`

DDL trên là thiết kế TO-BE, chưa được app runtime apply. Database không lưu raw user PII hoặc raw conversation; password dùng Argon2id và các field user/conversation dùng HMAC-SHA-256 digest.

## Build index

```powershell
python scripts/build_graphrag.py
```

Artifact được ghi vào `storage/graphrag/`:

- `legal_graphrag.sqlite`
- `documents.jsonl`
- `nodes.jsonl`
- `edges.jsonl`
- `chunks.jsonl`

## Chạy chatbot

Tạo `.env` từ `.env.example`, cấu hình Neo4j/Qdrant, đặt `GROQ_API_KEY` nếu muốn dùng LLM, rồi chạy:

```powershell
Set-Location F:\VlegalAI
python -m uvicorn app.main:app --app-dir . --host 0.0.0.0 --port 8000
```

Mở `http://localhost:8000`.

Nếu chưa đặt `GROQ_API_KEY`, app vẫn chạy ở chế độ retrieval-only và hiển thị các căn cứ GraphRAG liên quan. Runtime retrieval cần ít nhất một backend ngoài là Neo4j hoặc Qdrant.

## Dùng Neo4j local + Qdrant Cloud

1. Chạy Neo4j local không cần Docker.

Bạn có thể dùng Neo4j Desktop:

- Cài Neo4j Desktop.
- Tạo DBMS local, đặt password cho user `neo4j`.
- Start DBMS.
- Kiểm tra Neo4j Browser ở `http://localhost:7474`.
- Bolt URI mặc định: `bolt://localhost:7687`.

Hoặc dùng Neo4j service/console nếu đã cài Neo4j Server:

```powershell
neo4j console
```

2. Dùng Qdrant Cloud collection `laborcare_legal_chunks`.

Collection trong ảnh của bạn đang dùng:

- Dense vector name: `abstract-dense-vector`
- Dense vector size: `1536`
- Distance: `Cosine`
- Sparse vector name: `title-spare-vector`

Code hiện dùng dense vector `abstract-dense-vector`; sparse vector chưa bắt buộc.

3. Tạo `.env` từ `.env.example`, điền:

```env
RETRIEVER_BACKEND=hybrid_rag
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=<password>
NEO4J_DATABASE=neo4j
QDRANT_URL=https://<cluster>.qdrant.tech
QDRANT_API_KEY=<api-key>
QDRANT_COLLECTION=laborcare_legal_chunks
QDRANT_VECTOR_NAME=abstract-dense-vector
QDRANT_VECTOR_SIZE=1536
```

4. Sync graph và vector:

```powershell
python scripts/sync_external_graphrag.py --reset-neo4j --reset-qdrant
```

Script này rebuild SQLite intermediate từ `Data (1)`, sau đó:

- Upsert `LegalNode`, `LegalChunk` và quan hệ vào Neo4j.
- Upsert vectors + chunk payload vào Qdrant Cloud.

Nếu đã build SQLite rồi và chỉ muốn sync lại external:

```powershell
python scripts/sync_external_graphrag.py --skip-sqlite-build
```

5. Chạy app:

```powershell
Set-Location F:\VlegalAI
python -m uvicorn app.main:app --app-dir . --host 0.0.0.0 --port 8000
```

Các chế độ search:

- `rag`: chỉ dùng Qdrant Cloud để vector-search chunks.
- `graphrag`: chỉ dùng Neo4j local để fulltext-search chunks và mở rộng graph.
- `hybrid_rag`: Qdrant lấy ứng viên vector, Neo4j mở rộng graph.

Trong UI, người dùng chọn một trong 3 chế độ `RAG`, `GraphRAG`, `Hybrid RAG` ngay trên ô nhập câu hỏi. API cũng nhận trường `backend` trong `/api/chat` và `/api/search`; các alias cũ `qdrant`, `neo4j`, `hybrid`, `auto` vẫn còn dùng được để tương thích cấu hình hiện tại.

## Public bằng ngrok

```powershell
ngrok http 8000
```

Nếu ngrok yêu cầu tài khoản, cấu hình token:

```powershell
ngrok config add-authtoken <NGROK_AUTHTOKEN>
ngrok http 8000
```

## RAGAS evaluation

Install the evaluation dependencies:

```powershell
pip install -r requirements.txt
```

Smoke test the local SQLite GraphRAG index without calling evaluator LLMs:

```powershell
python scripts/evaluate_ragas.py --backends sqlite --limit 5 --top-k 10 --response-mode reference --prepare-only
```

Evaluate configured RAG and GraphRAG backends on `eval_legal_rag_graphrag_1000.json`:

```powershell
python scripts/evaluate_ragas.py --backends rag graphrag --top-k 10 --evaluator-provider groq --response-mode generate
```

Use `--evaluator-provider openai` if `OPENAI_API_KEY` is configured. Results are written under `storage/eval/ragas/<run-id>/`, including prepared RAGAS inputs, per-backend summaries, exact `chunk_id` retrieval metrics, RAGAS score CSV files, and `comparison.csv`.
