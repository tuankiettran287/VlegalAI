# BÁO CÁO ĐÁNH GIÁ KIẾN TRÚC, THIẾT KẾ VÀ AI ENGINEERING

## VLegalAI — RAG, GraphRAG và HybridRAG đa tầng

**Phiên bản tài liệu:** 2.1  
**Ngày đánh giá:** 13/07/2026  
**Phạm vi mã nguồn:** `F:\VlegalAI`  
**Logical/physical design:** `docs/design/VLegalAI_ERD.md`, `docs/design/VLegalAI_Physical_Database_Design.md`, `docs/design/mermaid/*.mmd` và `docs/design/sql/*.sql`  
**Model mục tiêu được nhóm xác nhận:** `DeepSeek-R1-Distill-Qwen-7B` (DeepSeek 7B)  
**Product modes:** `RAG`, `GRAPHRAG`, `HYBRID_RAG` — không có Local mode

> Đây là báo cáo readiness nội bộ theo checklist được cung cấp, không phải điểm chính thức của hội đồng. Kết quả chấm theo bằng chứng hiện diện trong bản bàn giao và phân biệt rõ kiến trúc mục tiêu TO-BE với source/runtime AS-IS.

[[PAGE_BREAK]]

## 1. Kiểm soát tài liệu

| Thuộc tính | Giá trị |
|---|---|
| Phiên bản | 2.1 |
| Thay đổi chính | Bổ sung Physical Database Design PostgreSQL cho user/chat; hash-only PII và conversation; DDL V001; checklist materialization; cập nhật ERD privacy fields |
| Artifact thiết kế | 1 system overview, 3 ERD đầy đủ, 5 ERD view rút gọn, logical/physical data dictionary, constraint catalogue và PostgreSQL DDL |
| Không thay đổi | Source runtime, dữ liệu, index, metric artifact và Git history; DDL mới là thiết kế TO-BE chưa apply |
| Quy ước | TO-BE = thiết kế mục tiêu; AS-IS = bằng chứng đang có trong repo/runtime |

## 2. Kết luận điều hành

Phiên bản 2.1 giữ Logical Design toàn hệ thống theo ba miền **Knowledge & Index**, **Runtime & Application**, và **Evaluation & MLOps**, đồng thời bổ sung Physical Database Design cho user/chat. Thiết kế pin DeepSeek 7B cho bước sinh câu trả lời và chỉ cho phép ba mode: RAG, GraphRAG, HybridRAG. HybridRAG chạy đúng hai nhánh RAG/Qdrant và GraphRAG/Neo4j rồi fusion; không có kho Hybrid riêng và không có Local mode.

Artifact ERD đóng khoảng trống logical design: có entity, thuộc tính, khóa, cardinality, ontology GraphRAG tám tầng, index/model version, retrieval trace, citation, contract/signature và experiment tracking. Physical design mới liệt kê table/field/type/size/default/constraint/index và logical mapping, với `APP_USER` bắt buộc lưu identity dạng hash và có `conversation_hash`. Vì vậy **D3.1 đạt về tài liệu Logical Design**; D3.2 vẫn “Một phần” cho tới khi DDL được apply và có bằng chứng introspection/test.

Source AS-IS chưa khớp hoàn toàn với target: FastAPI đang gọi Groq và mặc định `llama-3.3-70b-versatile`; UI/API còn công bố `local_graphrag` và có SQLite fallback; implementation hybrid hiện dùng Qdrant candidates để mở rộng Neo4j thay vì ghi trace hai pipeline độc lập rồi fusion. Notebook có cấu hình DeepSeek-R1-Distill-Qwen-7B nhưng chưa có output thực thi để nối với production run.

| Phạm vi | Đạt | Một phần | Chưa đạt | Không áp dụng | Tổng |
|---|---:|---:|---:|---:|---:|
| Toàn bộ tiêu chí | 7 | 20 | 8 | 3 | 38 |
| Chỉ tiêu chí Mandatory | 6 | 8 | 5 | 0 | 19 |

Các blocker quan trọng:

- **P0 Security:** credential thật nằm trong `.env`; Google service-account private key nằm trong `env.json`; không có `.gitignore`. Phải coi khóa đã lộ và rotate/revoke.
- **Git/Team evidence:** thư mục dự án không có repository Git có lịch sử; không chứng minh được đóng góp AI của nhiều thành viên.
- **Model conformance:** DeepSeek 7B là model mục tiêu nhưng production path trong source vẫn là Groq/Llama; thiếu run manifest chứng minh model thực dùng.
- **Hybrid conformance:** target là fusion hai nhánh độc lập; source hiện là Qdrant-seeded Neo4j expansion và chưa có benchmark HybridRAG.
- **AI training:** không có model được train end-to-end trên dataset dự án và không có training pipeline/seed/checkpoint.
- **Production readiness:** thiếu auth/rate limit, privacy control, test suite/CI, DB migration/constraint và experiment tracking.

## 3. Phạm vi, phương pháp và quy ước

Đánh giá dựa trên source Python/TypeScript, README và tài liệu GraphRAG, SQLite/JSONL, Neo4j/Qdrant integration code, notebook, dataset 1.000 mẫu, artifact đánh giá, runtime UI/API và metadata Git tại máy bàn giao.

| Trạng thái | Ý nghĩa |
|---|---|
| Đạt | Có artifact/bằng chứng đủ để trả lời tiêu chí; nếu chỉ là thiết kế thì ghi rõ phạm vi thiết kế. |
| Một phần | Có triển khai hoặc tài liệu đáng kể nhưng còn thiếu view, kiểm chứng, contract hoặc còn sai lệch AS-IS/TO-BE. |
| Chưa đạt | Không tìm thấy bằng chứng hoặc bằng chứng mâu thuẫn trực tiếp với tiêu chí. |
| Không áp dụng | Ngoài phạm vi kiến trúc hiện tại; cần hội đồng chấp thuận nếu rubric chấm literal. |

Các kiểm tra kế thừa từ audit trước: parse 8/8 file Python pass; `tsc --noEmit` pass; SQLite integrity `ok`; corpus 56 DOCX, 57 record document, 23.633 node, 51.094 edge, 25.554 chunk; kiểm tra toàn bộ 1.000 mẫu evaluation; smoke test `/api/chat` trả HTTP 200 trên input thật; UI desktop/mobile render được.

[[PAGE_BREAK]]

## 4. Kiến trúc mục tiêu và sai lệch AS-IS

### 4.1 System overview TO-BE

[[DIAGRAM:output/docx_work/system_overview.png|Hình 1 — Kiến trúc mục tiêu: ba mode, hai nhánh retrieval và DeepSeek 7B|6.35]]

Nguyên tắc điều phối:

- RAG chạy một nhánh vector trên Qdrant.
- GraphRAG chạy một nhánh graph trên Neo4j.
- HybridRAG chạy đúng hai nhánh trên, chuẩn hóa score, fusion và tạo final hit duy nhất theo chunk.
- Chỉ final hit được dùng để dựng citation và grounded context cho DeepSeek 7B.
- SQLite chỉ là staging/build artifact, không phải product mode.

### 4.2 Target–AS-IS conformance

| Hạng mục | Target declaration | Source AS-IS | Kết luận |
|---|---|---|---|
| Generation model | DeepSeek-R1-Distill-Qwen-7B | Notebook cấu hình DeepSeek 7B; production FastAPI gọi Groq và mặc định Llama 3.3 70B | Chưa xác nhận DeepSeek integration end-to-end |
| RAG | Qdrant/vector branch | Có Qdrant store và mode `rag` | Có bằng chứng đáng kể |
| GraphRAG | Neo4j/graph branch | Có Neo4j store và mode `graphrag` | Có bằng chứng đáng kể |
| HybridRAG | Hai branch độc lập rồi fusion | Qdrant lấy candidate, Neo4j mở rộng; chưa có `FusionRun`/contribution trace | Một phần |
| Local mode | Không thuộc product contract | UI/API còn `local_graphrag`, alias SQLite và fallback | Sai lệch cần loại khỏi UI/contract |
| Hybrid evaluation | Run riêng trên test freeze | Chưa có artifact HybridRAG | Chưa chứng minh hiệu quả |

[[SECTION:LANDSCAPE]]

### 4.3 Ma trận API và shared resource AS-IS

| Endpoint | Request | Response chính | Resource đọc | Resource ghi | External | Persistence | Owner/gap |
|---|---|---|---|---|---|---|---|
| `GET /api/stats` | Query backend tùy chọn | Store stats, backend options, model readiness | Retriever store, env/config | Không | Neo4j/Qdrant health khi khởi tạo store | Không | Lộ `local_graphrag` và model Groq AS-IS |
| `GET /api/laws/search` | `q`, `limit` | Danh sách văn bản | `documents.jsonl` | Không | Không | Không | File scan; chưa có version/effectivity contract |
| `GET /api/templates` | Không | Contract template metadata | Constant in-memory | Không | Không | Không | Template bị nhân đôi frontend/backend |
| `POST /api/search` | Query, top-k, backend | Retrieval hits | Qdrant/Neo4j/Hybrid; SQLite fallback AS-IS | Không | Qdrant, Neo4j | Không | Response chưa được version hóa; target không có Local |
| `POST /api/chat` | Question, top-k, backend | Answer, sources, backend/model metadata | Retriever store, prompt | Không persist chat/session | Groq AS-IS; DeepSeek 7B TO-BE | Không | Thiếu durable trace run/branch/fusion/citation |
| `POST /api/contracts/draft` | Contract data/template | Draft text | Template/prompt | Không | Groq AS-IS | Không | Chưa có Contract/ContractVersion store |
| `POST /api/contracts/review` | Contract text | Summary/findings | Retrieval context, prompt | Không | Groq AS-IS | Không | Chưa persist Review/Finding/Evidence |
| `POST /api/contracts/compare` | Original/revised text | Comparison | Prompt | Không | Groq AS-IS | Không | Chưa persist version/comparison |
| `POST /api/signatures/prepare` | Document/signers | Hash package/status | Request payload | Không | Không | Không | Demo; không có SignaturePacket/Event audit store |
| `POST /api/feedback` | Rating/category/comment | Acknowledgement | Request context | `feedback.jsonl` | Không | JSONL | Chưa FK tới user/session/message |

[[SECTION:PORTRAIT]]

### 4.4 D2 — Architecture Design

| ID | Mandatory | Trạng thái | Đánh giá |
|---|:---:|---|---|
| D2.1 | Có | **Một phần** | Có system overview mục tiêu và mô tả runtime/build; vẫn thiếu deployment view chính thức với node/port/protocol/trust boundary. Target DeepSeek/ba mode chưa khớp source Groq/Local fallback. |
| D2.2 | Có | **Một phần** | Luồng RAG, GraphRAG và Hybrid hai nhánh đã được mô hình hóa; luồng AS-IS hybrid không phải independent-branch fusion và chưa có activity/sequence trace cho contract, signature, feedback, failure/fallback. |
| D2.3 | Không | **Một phần** | Có lớp builder/store và phân rã khái niệm nhưng chưa có package/component diagram, dependency direction hay interface ownership. `main.py` và `App.tsx` còn monolithic. |
| D2.4 | Không | **Một phần** | Báo cáo đã bổ sung endpoint–resource matrix; source vẫn thiếu versioned OpenAPI response/error/auth contract, durable ownership và còn dữ liệu/constant nhân đôi. |

Kết luận D2: thiết kế mục tiêu đã rõ hơn, nhưng ERD không thay thế deployment, process, package và component views. Cần version hóa C4/deployment/sequence cùng source và đóng sai lệch DeepSeek/Local/Hybrid.

[[PAGE_BREAK]]

## 5. D3 — Detail Design và ERD Mermaid

### 5.1 Phạm vi ERD

ERD phiên bản 2.0 là Logical Design TO-BE. View rút gọn trên trang khổ lớn giữ entity/cardinality; source Mermaid đầy đủ chứa toàn bộ thuộc tính tại:

- `docs/design/mermaid/knowledge_index_erd.mmd`
- `docs/design/mermaid/runtime_hybrid_erd.mmd`
- `docs/design/mermaid/evaluation_mlops_erd.mmd`

Các entity TO-BE không được dùng làm bằng chứng rằng physical schema đã tồn tại.

[[SECTION:TABLOID]]

### 5.2 ERD — Knowledge & Index

[[DIAGRAM:output/docx_work/knowledge_index_overview.png|Hình 2 — Knowledge base, graph tám tầng, chunk, embedding và index version|15.7]]

[[SECTION:PORTRAIT]]

### 5.3 Entity dictionary — Knowledge & Index

| Entity | PK | FK/Unique chính | Thuộc tính trọng yếu | Intended store / trạng thái |
|---|---|---|---|---|
| `ISSUING_AUTHORITY` | `authority_id` | tên chuẩn hóa | name, authority_type, country_code | PostgreSQL; TO-BE |
| `LEGAL_DOCUMENT` | `document_id` | authority_id; canonical_code unique | title, type, jurisdiction | PostgreSQL; map một phần `docs` |
| `DOCUMENT_VERSION` | `document_version_id` | document_id; unique document/version | publish/effective dates, legal_status, checksum | PostgreSQL/object storage; chưa có bảng |
| `VERSION_EFFECT` | `version_effect_id` | source_version_id, target_version_id | effect_type, effective_on, affected_scope | PostgreSQL/Neo4j projection; chưa có |
| `KNOWLEDGE_LAYER` | `layer_id` | code/ordinal unique | ordinal 1–8, name, description | PostgreSQL reference; TO-BE |
| `INDEX_VERSION` | `index_version_id` | version_name unique | source manifest hash, config hash, status | PostgreSQL; chưa có |
| `INDEX_DOCUMENT` | `index_document_id` | index_version_id, document_version_id | parse_status, parsed_checksum | PostgreSQL; chưa có |
| `KNOWLEDGE_NODE` | `node_id` | index/layer/document/parent | node_type, canonical_key, text, confidence | Neo4j + metadata; map `nodes` |
| `KNOWLEDGE_RELATION` | `relation_id` | source/target/index | relation_type, weight, extractor, confidence | Neo4j + metadata; map `edges` |
| `TEXT_CHUNK` | `chunk_id` | index/document/node | text, token/offset, checksum | PostgreSQL/object store + projections; map `chunks` |
| `RELATION_EVIDENCE` | `relation_evidence_id` | relation_id, chunk_id | span, evidence text, confidence | PostgreSQL; evidence AS-IS là text rời |
| `MODEL_VERSION` | `model_version_id` | provider/name/revision/role | dimensions, URI, checksum | Model registry; chưa có |
| `CHUNK_EMBEDDING` | `embedding_id` | unique index/chunk/model | dimensions, vector_ref, input checksum | Qdrant + metadata; provenance thiếu |
| `INDEX_MATERIALIZATION` | `materialization_id` | index_version_id | backend, locator, schema, checksum, status | PostgreSQL; chưa có |

### 5.4 GraphRAG tám tầng

| Tầng | Mã | Ý nghĩa | Ví dụ |
|---:|---|---|---|
| 1 | `STRUCTURE` | Cấu trúc/liên kết văn bản | Văn bản–chương–mục–điều–khoản–điểm |
| 2 | `TERMINOLOGY` | Thuật ngữ/định nghĩa/công thức | `ĐƯỢC_ĐỊNH_NGHĨA_TẠI` |
| 3 | `DOMAIN` | Chủ thể, quyền, nghĩa vụ, điều kiện | `CÓ_QUYỀN`, `CÓ_NGHĨA_VỤ` |
| 4 | `TEMPORAL_STATE` | Hiệu lực, thời hạn, trạng thái | `CÓ_HIỆU_LỰC_TỪ`, `CHUYỂN_TRẠNG_THÁI` |
| 5 | `PROCEDURE` | Thủ tục, hồ sơ, cơ quan, deadline | `YÊU_CẦU_HỒ_SƠ`, `THỰC_HIỆN_BỞI` |
| 6 | `LIFECYCLE` | Vòng đời nghiệp vụ | Giao kết → thực hiện → chấm dứt |
| 7 | `COMPLIANCE_RISK` | Cấm, chế tài, rủi ro | `BỊ_CẤM`, `CÓ_CHẾ_TÀI` |
| 8 | `PRECEDENT` | Án lệ/quyết định/tình huống tương tự | `ÁP_DỤNG_TRONG`, `TƯƠNG_TỰ` |

[[SECTION:TABLOID]]

### 5.5 ERD — Runtime retrieval, fusion và generation

[[DIAGRAM:output/docx_work/runtime_retrieval_overview.png|Hình 3 — Trace RAG/GraphRAG/HybridRAG từ session tới final citation và DeepSeek 7B|15.7]]

[[SECTION:PORTRAIT]]

### 5.6 Quy tắc mode, branch và model

| Mode | Branch | Backend | Fusion |
|---|---|---|---|
| `RAG` | đúng 1 `RAG` | Qdrant | không |
| `GRAPHRAG` | đúng 1 `GRAPHRAG` | Neo4j | không |
| `HYBRID_RAG` | đúng 2: RAG + GRAPHRAG | Qdrant + Neo4j | đúng 1 `FUSION_RUN` |

- `UNIQUE(retrieval_run_id, branch_type)`; không có branch thứ ba hoặc Local fallback trong target.
- Hai branch Hybrid dùng cùng `index_version_id`; run chỉ success khi cả hai hoàn tất.
- Cùng một chunk từ hai branch tạo một final hit và hai `HIT_CONTRIBUTION`.
- Citation chỉ tham chiếu final hit.
- `MODEL_VERSION` cho generation pin family DeepSeek, model `DeepSeek-R1-Distill-Qwen-7B`, scale 7B, revision và checksum.

### 5.7 Entity dictionary — Runtime retrieval

| Nhóm | Entity | Khóa/liên kết | Thuộc tính trọng yếu | Trạng thái AS-IS |
|---|---|---|---|---|
| Identity/chat | `APP_USER`, `RAG_SESSION`, `CHAT_MESSAGE` | user → session → message | role, content, status, timestamps | UI state/transient; chưa durable |
| Run | `RETRIEVAL_RUN` | message, index_version | mode, normalized query, top-k, status, timing | Chưa persist |
| Branch | `RETRIEVAL_BRANCH`, `BRANCH_HIT` | run → branch → chunk/node | branch_type, backend, rank, score, hops | Store trả hit nhưng chưa có entity trace |
| Fusion | `FUSION_RUN`, `RETRIEVAL_HIT`, `HIT_CONTRIBUTION` | run/fusion/final hit/raw hit | method, weights, normalized/weighted score | Chưa có durable fusion trace |
| Generation | `MODEL_VERSION`, `PROMPT_VERSION`, `GENERATION_RUN` | run + model + prompt | attempt, tokens, latency, status | Source gọi Groq; chưa pin DeepSeek run |
| Citation | `ANSWER_CITATION` | answer_message + final_hit | cited span, answer offsets, validation | Sources trả về response; chưa persist/validate |
| Feedback | `USER_FEEDBACK` | user/session/message | rating, category, comment | JSONL, chưa FK |

[[SECTION:TABLOID]]

### 5.8 ERD — Contract, review và signature

[[DIAGRAM:output/docx_work/contract_signature_overview.png|Hình 4 — Phiên bản hợp đồng, review evidence và append-only signature audit|15.7]]

[[SECTION:PORTRAIT]]

| Nhóm | Entity chính | Quy tắc |
|---|---|---|
| Contract | `CONTRACT`, `CONTRACT_VERSION` | Unique contract/version; version ký là immutable; previous_version tạo lịch sử |
| Review | `CONTRACT_REVIEW`, `REVIEW_FINDING`, `CONTRACT_EVIDENCE` | Finding thuộc review; evidence phải truy về final retrieval hit |
| Signature | `SIGNATURE_PACKET`, `PACKET_SIGNER`, `SIGNATURE_EVENT` | Packet có signer order; event append-only và chain hash |

[[SECTION:TABLOID]]

### 5.9 ERD — Dataset và evaluation cases

[[DIAGRAM:output/docx_work/dataset_evaluation_overview.png|Hình 5 — Dataset version, frozen split, ground truth và per-case result|15.7]]

[[SECTION:TABLOID]]

### 5.10 ERD — Experiment tracking và MLOps

[[DIAGRAM:output/docx_work/experiment_mlops_overview.png|Hình 6 — Run pin dataset/index/model/prompt và sinh metric, error, comparison, artifact|15.7]]

[[SECTION:PORTRAIT]]

### 5.11 Entity dictionary — Evaluation & MLOps

| Nhóm | Entity | Khóa/liên kết | Thuộc tính trọng yếu | Trạng thái AS-IS |
|---|---|---|---|---|
| Dataset | `DATASET_VERSION`, `DATA_SPLIT` | dataset → split | manifest/checksum, seed, split_name, frozen | File 1.000 mẫu không có split manifest |
| Ground truth | `EVAL_CASE`, `GROUND_TRUTH_EVIDENCE`, `ANNOTATION_REVIEW` | split → case → chunk/document | question, reference, grade, span, reviewer | Label tự sinh; thiếu reviewer log |
| Experiment | `EXPERIMENT`, `EXPERIMENT_RUN` | experiment + dataset/index/prompt | retrieval_mode, git SHA, config/env hash, seed | Folder timestamp; thiếu run registry |
| Model/prompt | `MODEL_VERSION`, `PROMPT_VERSION`, `RUN_MODEL_BINDING` | run ↔ model/prompt | role, revision, checksum, template hash | Chưa pin đầy đủ |
| Results | `CASE_RESULT`, `CASE_RETRIEVAL` | run + case + chunk | answer, rank, score, latency/tokens | CSV/JSONL artifact |
| Metrics | `METRIC_DEFINITION`, `METRIC_OBSERVATION` | metric + run + optional case | formula version, scope, value, N | Summary CSV, chưa registry |
| Analysis | `ERROR_CASE`, `RUN_COMPARISON`, `RUN_ARTIFACT` | case/run/metric | category/root cause/remediation/delta/checksum | Chưa có structured error report/tracking |

### 5.12 Ràng buộc xuyên miền

- `DOCUMENT_VERSION`, `INDEX_VERSION`, dataset đã frozen/active phải immutable.
- Node, relation, chunk và embedding phải cùng index version.
- Qdrant/Neo4j materialization phải cùng source manifest/config checksum.
- `UNIQUE(run_id, eval_case_id)`; baseline/candidate phải cùng dataset/split/metric definition.
- Contract evidence và answer citation phải truy ngược tới final hit của retrieval run đã ground generation tương ứng.

### 5.13 Logical–physical mapping AS-IS

| Logical object | Materialization AS-IS | Ghi chú |
|---|---|---|
| Legal document/version | SQLite `docs`; `documents.jsonl` | Một record gộp document/version; thiếu effectivity history |
| Knowledge node | SQLite `nodes`; Neo4j `:LegalNode`; `nodes.jsonl` | `node_type` multiplex tầng; thiếu index_version |
| Knowledge relation | SQLite `edges`; Neo4j relationship động; `edges.jsonl` | evidence text; thiếu registry/provenance/version |
| Text chunk | SQLite `chunks`; Neo4j `:LegalChunk` + `CHUNK_OF`; Qdrant payload | Link bằng doc/node/chunk ID; thiếu checksum/version contract |
| Embedding | `chunks.vector`; Qdrant named vector 1536/cosine | Feature hash, chưa phải learned semantic embedding; thiếu model provenance |
| Full-text | SQLite `chunk_fts`; Neo4j `legal_chunk_fulltext` | Derived index |
| Index version/materialization | Chưa có | Chỉ suy ra từ config/folder/build time |
| Chat/retrieval/generation/citation | Không durable | Không có run/branch/fusion trace |
| Contract/review/signature | Không durable | Kết quả transient; signature demo không persist |
| Feedback | `feedback.jsonl` | Chưa FK user/session/message |
| Evaluation/MLOps | JSON/JSONL/CSV | Chưa MLflow/W&B/registry/run manifest đầy đủ |

### 5.14 Physical data dictionary AS-IS

| Store/object | Field/property | Type/size | Null/default/key | Logical mapping |
|---|---|---|---|---|
| SQLite `docs` | `doc_id`; filename, path, title, code, doc_type, issuer, text | `TEXT`; không khai báo length | `doc_id` PK; các field khác nullable; không default/FK | LegalDocument + DocumentVersion bị gộp |
| SQLite `nodes` | node_id, doc_id, node_type, label, number, title, parent_id, path_label, text, ordinal | `TEXT`, `INTEGER` | node_id PK; nullable; không FK/default/check | KnowledgeNode |
| SQLite `edges` | edge_id, source_id, target_id, relation, evidence | `TEXT` | edge_id PK; nullable; không FK/default/check | KnowledgeRelation/Evidence bị gộp |
| SQLite `chunks` | chunk_id, doc_id, node_id, chunk_type, title, path_label, citation, text, token_count, ordinal, vector | `TEXT`, `INTEGER`, `BLOB` | chunk_id PK; nullable; không FK/default/check | TextChunk + Embedding bị gộp |
| SQLite `chunk_fts` | chunk_id, title, path_label, citation, text | FTS5 unicode61 | chunk_id unindexed; derived; không FK | Full-text projection |
| SQLite indexes | nodes(parent); nodes(doc,type); edges(source,relation); edges(target,relation); chunks(node); chunks(doc) | B-tree secondary | Có index; không unique | Query acceleration |
| Neo4j `LegalNode` | node_id, doc_id, node_type, label, number, title, parent_id, path_label, text, ordinal | Property graph | unique node_id; indexes type/doc | KnowledgeNode projection |
| Neo4j `LegalChunk` | chunk_id, doc_id, node_id, type/title/citation/text/token/ordinal | Property graph | unique chunk_id; indexes node/type; fulltext title/citation/text | TextChunk projection |
| Neo4j relations | `CHUNK_OF` và legal relationship động | Relationship + properties | Chưa có relation-type registry/version | KnowledgeRelation projection |
| Qdrant collection | named vector `abstract-dense-vector`, payload chunk fields | 1536 float, cosine | point theo chunk; payload indexes theo code | ChunkEmbedding projection AS-IS |

[[SECTION:TABLOID]]

### 5.15 Physical Database Design TO-BE — user và hội thoại

Đặc tả triển khai chi tiết: `docs/design/VLegalAI_Physical_Database_Design.md`. DDL PostgreSQL 16+: `docs/design/sql/V001__runtime_user_privacy.sql`.

Nguyên tắc bắt buộc: database không lưu user PII, credential, query hoặc conversation content dạng rõ. Password dùng Argon2id có salt riêng; email/tên/điện thoại/profile/query/message/feedback dùng HMAC-SHA-256 có khóa và lưu hex `CHAR(64)`. Khóa HMAC nằm trong secret manager, database chỉ lưu `hash_key_version`. `user_id`, role/status và timestamp là metadata do hệ thống sinh để giữ PK/FK/audit, không phải thông tin nhận dạng do user cung cấp nên không hash.

[[DIAGRAM:output/docx_work/physical_user_chat_overview.png|Hình 7 — PostgreSQL physical ERD cho user, session, message, retrieval và feedback theo hash-only policy|15.7]]

[[SECTION:PORTRAIT]]

| Physical table | Logical mapping | PK/FK chính | User/conversation field | Default/constraint chính |
|---|---|---|---|---|
| `app_user` | `APP_USER` | PK user_id | email_hash, display_name_hash, phone_hash, organization_hash, password_hash, profile_hash, conversation_hash | UUID generated; email unique; role USER; status ACTIVE; hash key version 1 |
| `rag_session` | `RAG_SESSION` | PK session_id; FK user_id | title_hash, conversation_hash | status ACTIVE; timestamps current; cascade theo user |
| `chat_message` | `CHAT_MESSAGE` | PK message_id; FK session/parent | message_content_hash | status COMPLETED; token_count 0; role/status check |
| `retrieval_run` | `RETRIEVAL_RUN` | PK run_id; FK request_message | normalized_query_hash | top-k 10; mode/status/range/time check |
| `user_feedback` | `USER_FEEDBACK` | PK feedback_id; FK user/session/message | comment_hash, page_hash | rating 1–5; timestamp current |

`APP_USER.conversation_hash` là một rolling digest tùy chọn của lịch sử hội thoại. `RAG_SESSION.conversation_hash` xác nhận transcript theo thứ tự và `CHAT_MESSAGE.message_content_hash` xác nhận từng message. Các hash này không thể giải mã; nội dung rõ chỉ tồn tại tạm thời trong runtime để sinh câu trả lời.

[[SECTION:TABLOID]]

### 5.16 Physical field list — `app_user`

| Field | PostgreSQL type/size | Null/default | Key/check | Logical mapping |
|---|---|---|---|---|
| `user_id` | UUID / 16 bytes | NOT NULL / generated UUID | PK | `APP_USER.user_id` |
| `email_hash` | CHAR(64) | NOT NULL / none | UNIQUE; lowercase hex | email → HMAC hash |
| `display_name_hash` | CHAR(64) | NOT NULL / none | lowercase hex | display_name → HMAC hash |
| `phone_hash` | CHAR(64) | NULL / NULL | lowercase hex khi có | phone → HMAC hash |
| `organization_hash` | CHAR(64) | NULL / NULL | lowercase hex khi có | organization → HMAC hash |
| `password_hash` | VARCHAR(255) | NOT NULL / none | prefix `$argon2id$` | password → salted hash |
| `profile_hash` | CHAR(64) | NOT NULL / none | lowercase hex | canonical profile digest |
| `conversation_hash` | CHAR(64) | NULL / NULL | lowercase hex khi có | rolling conversation digest |
| `role_code` | VARCHAR(32) | NOT NULL / `USER` | USER/REVIEWER/ADMIN | system role |
| `account_status` | VARCHAR(16) | NOT NULL / `ACTIVE` | controlled status | account status |
| `hash_algorithm` | VARCHAR(32) | NOT NULL / `HMAC-SHA-256` | fixed check | hash policy |
| `hash_key_version` | SMALLINT / 2 bytes | NOT NULL / 1 | > 0 | key rotation metadata |
| `created_at` | TIMESTAMPTZ / 8 bytes | NOT NULL / current timestamp | audit | created_at |
| `updated_at` | TIMESTAMPTZ / 8 bytes | NOT NULL / current timestamp | app updates on mutation | updated_at |

[[SECTION:PORTRAIT]]

### 5.17 Materialization checklist và kết luận D3.2

| Kiểm tra | Design evidence | Runtime evidence cần có | Trạng thái |
|---|---|---|---|
| Tables | Table list + DDL V001 | `information_schema.tables` | Thiết kế đạt; runtime pending |
| Fields/type/size | Field dictionary | `information_schema.columns` | Thiết kế đạt; runtime pending |
| Null/default | Field dictionary + DDL | column nullability/default query | Thiết kế đạt; runtime pending |
| PK/FK/unique/check | Named constraints trong DDL | `pg_constraint` + negative tests | Thiết kế đạt; runtime pending |
| Index | DDL index statements | `pg_indexes` + query plan | Thiết kế đạt; runtime pending |
| Logical mapping | Logical-to-physical matrix | Traceability review | Đạt ở tài liệu |
| Hash-only user data | Hash policy + hash fields | DB/log/backup scan + negative tests | Thiết kế đạt; runtime pending |
| Migration | Versioned file V001 | migration history/checksum | File có; chưa apply |

**Answer to the criterion:** Physical Design này represent materialization ở mức implementation-ready specification. Chưa được tuyên bố là materialized into the running system cho tới khi migration được apply, introspection khớp thiết kế và test xác nhận không có raw user/conversation data.

### 5.18 D3 — Detail Design

| ID | Mandatory | Trạng thái | Đánh giá |
|---|:---:|---|---|
| D3.1 | Có | **Đạt — Logical Design** | ERD Mermaid v2 bao phủ ba miền, entity/attribute/key/cardinality và cross-store ID; mô hình đúng ba mode, Hybrid hai nhánh và DeepSeek 7B. Đây là deliverable thiết kế TO-BE, không phải chứng nhận physical implementation. |
| D3.2 | Có | **Một phần — design complete, runtime pending** | Đã có AS-IS dictionary cho SQLite/Neo4j/Qdrant và TO-BE PostgreSQL DDL cho user/session/message/retrieval/feedback, gồm field size/type/default/FK/check/index và logical mapping. Chưa apply migration, chưa có introspection/integration test; Runtime/MLOps còn chưa materialize đầy đủ. |
| D3.3 | Không | **Một phần** | 7 route, validation cơ bản, theme và responsive; runtime desktop/mobile hoạt động. Thiếu screen inventory/spec/flow và một số interaction còn demo/không có handler/mobile overlap. |
| D3.4 | Không | **Một phần** | Có builder/store/config classes nhưng thiếu class/sequence/control-flow diagram, shared retriever interface và invariant từng unit; logic còn trộn/lặp. |
| D3.5 | Có | **Chưa đạt** | ERD có field trạng thái nhưng không thay state diagram/state machine. Chưa có diagram cho legal effectivity, ingestion/index, chat, contract/review/signature. |

[[PAGE_BREAK]]

## 6. P5 — Technology Choices for Software Architecture

| ID | Mandatory | Trạng thái | Đánh giá |
|---|:---:|---|---|
| P5.1 | Có | **Một phần** | Qdrant cho RAG, Neo4j cho GraphRAG và LLM cho generation là phân vai hợp lý. Tuy nhiên API thiếu auth/rate limit; CORS mở; dữ liệu hợp đồng có thể gửi dịch vụ ngoài mà chưa có consent/PII redaction/DPA; timeout/retry/circuit breaker chưa đầy đủ. |
| P5.2 | Không | **Một phần** | React, TypeScript, Vite, strict type checking và API abstraction là stack phù hợp. Thiếu lint/formatter/test/accessibility regression; `App.tsx` monolithic và runtime/types có độ lệch phiên bản. |
| P5.3 | Không | **Một phần** | FastAPI REST/Pydantic, Qdrant/Neo4j stores phù hợp cho prototype. Thiếu response model/versioned contract/DI/lifespan cleanup; sync network I/O trong route; broad exception; target DeepSeek/ba mode chưa đồng nhất production source. |
| P5.4 | Không | **Không áp dụng** | Không có native mobile stack; sản phẩm là responsive web. Nếu rubric bắt buộc app mobile riêng, cần đổi thành Chưa đạt. |

Kết luận P5: stack có năng lực triển khai RAG/GraphRAG, nhưng technology choice chỉ được xem là đúng khi product contract, model version, privacy/security và operational controls được thực thi nhất quán.

## 7. P6 — Application of Computing Knowledge

| ID | Mandatory | Trạng thái | Đánh giá |
|---|:---:|---|---|
| P6.1 | Có | **Một phần** | Python dùng snake_case/type hints; TypeScript strict; parse/type-check pass. Thiếu lint/formatter/backend type-check/test/CI; file lớn và nhiều `except Exception`; CLI có rủi ro encoding Windows. |
| P6.2 | Không | **Một phần** | Có config dataclass, Builder và store encapsulation. Thiếu `Protocol`/ABC cho retriever, dùng `Any`, service/repository boundary yếu, graph expansion/fusion logic chưa tách và kiểm thử theo SOLID. |
| P6.3 | Không | **Chưa đạt — Critical** | `.env` chứa credential thật; `env.json` chứa private key; không có `.gitignore`. Backend mode/model còn raw string/alias và target DeepSeek/không-Local không được enforce. Phải rotate/revoke và dùng secret manager. |
| P6.4 | Không | **Một phần** | Có Builder, Strategy/Factory-like store selection và fallback chain. Pattern còn ngầm định, không có typed interface/DI; target Hybrid fusion chưa được thể hiện bằng component/run objects. |
| P6.5 | Không | **Một phần** | Naming/PK/index tương đối rõ; Neo4j có unique constraints. SQLite không có FK/NOT NULL/CHECK/default/migration/schema version và build xóa/tạo lại DB. |

## 8. P7 — Complexity of Algorithm / Internal Processing

| ID | Mandatory | Trạng thái | Đánh giá |
|---|:---:|---|---|
| P7.1 | Có | **Đạt** | Bài toán trợ lý pháp lý dựa trên corpus, retrieval và grounded generation được nêu rõ; target phân biệt RAG, GraphRAG và HybridRAG. Cần bổ sung acceptance threshold, phạm vi hiệu lực và disclaimer pháp lý. |
| P7.2 | Có | **Một phần — rủi ro cao** | Parse/chunk/index + vector/graph/fusion là hướng đúng. AS-IS vector là feature hashing chứ không phải semantic embedding; local vector scan tuyến tính; graph có relation sai/typo; smoke query xếp sai chủ thể; Hybrid chưa phải two-branch fusion như target. |
| P7.3 | Không | **Một phần** | FastAPI/Pydantic/Neo4j/Qdrant/LLM/RAGAS là thư viện phù hợp. Chưa có semantic embedding/reranker benchmark tiếng Việt pháp lý, dependency lock đầy đủ và DeepSeek runtime adapter được kiểm chứng. |
| P7.4 | Không | **Một phần** | Có custom graph tám tầng, legal parsing, lifecycle/risk rules, propagation và fallback. Chưa chứng minh cải thiện: GraphRAG thua RAG baseline; chưa có Hybrid benchmark/ablation/fusion comparison. |

Smoke test truy vấn quyền đơn phương chấm dứt hợp đồng của người lao động xếp Điều 36 về quyền của người sử dụng lao động ở hạng 1, trong khi Điều 35 đúng đối tượng ở hạng 5. Đây là rủi ro ranking quan trọng cho miền pháp lý.

[[PAGE_BREAK]]

## 9. AI-Specific Criteria

### 9.1 Data Processing Pipeline

| ID | Mandatory | Trạng thái | Đánh giá |
|---|:---:|---|---|
| AI-DP.1 | Có | **Một phần** | Có đọc/normalize DOCX, graph build, hierarchical/sliding chunk và index. Dataset 1.000 mẫu không có train/validation/test split manifest; evaluator chỉ dùng offset/limit. |
| AI-DP.2 | Không | **Không áp dụng** | Không có supervised training/class imbalance workflow. Nếu fine-tune embedding/reranker thì augmentation/oversampling chỉ áp dụng train, không áp dụng test. |
| AI-DP.3 | Không | **Một phần** | 1.000 ID/question/reference/context hợp lệ và chunk ID tồn tại. Label tự sinh, thiếu generator script/guideline/reviewer log/IAA; citation parse có lỗi và 80% context tập trung ở hai tài liệu. |

### 9.2 AI Model Implementation

| ID | Mandatory | Trạng thái | Đánh giá |
|---|:---:|---|---|
| AI-MI.1 | Có | **Chưa đạt** | Không có optimizer/loss/backward/epoch/checkpoint/model artifact được train trên dataset dự án. DeepSeek 7B là pretrained model; load/eval hoặc gọi API không phải end-to-end training. |
| AI-MI.2 | Có | **Chưa đạt** | Không có training pipeline/seed/checkpoint/lockfile. Notebook DeepSeek chưa có executed output; artifact không truy được về code/model revision cụ thể. |
| AI-MI.3 | Không | **Không áp dụng có điều kiện** | Không có LoRA/PEFT/fine-tuning. Có thể N/A cho RAG dùng pretrained model nếu hội đồng chấp thuận; nếu rubric yêu cầu literal training thì đổi thành Chưa đạt. |
| AI-MI.4 | Có | **Đạt cho inference prototype** | `/api/chat` có retrieve → grounded prompt → LLM → sources và runtime input thật trả 200. Trạng thái này không xác nhận production đang dùng DeepSeek 7B; source hiện gọi Groq/Llama. |

### 9.3 Experimental Results & Evaluation

| ID | Mandatory | Trạng thái | Đánh giá |
|---|:---:|---|---|
| AI-ER.1 | Có | **Đạt cho retrieval** | Artifact 1.000 mẫu báo cáo hit@10, precision, recall, MRR và latency cho RAG/GraphRAG. Chưa có answer-quality/RAGAS đầy đủ và chưa có metric HybridRAG. |
| AI-ER.2 | Có | **Đạt** | RAG/Qdrant và GraphRAG/Neo4j chạy trên cùng 1.000 mẫu, top-k=10. Chưa có BM25-only, semantic embedding, HybridRAG hoặc ablation; nhưng baseline comparison tối thiểu đã có. |
| AI-ER.3 | Có | **Một phần** | Evaluation file tách khỏi corpus build và không có model training. Thiếu frozen split manifest, dataset hash/version, contamination/tuning log nên chưa xác nhận held-out độc lập. |
| AI-ER.4 | Không | **Chưa đạt** | Không có structured failure taxonomy/report của nhóm; notebook chỉ có cell in miss chưa chạy. Phân tích tại báo cáo này là audit mới, không phải artifact thực nghiệm đã version hóa. |

### 9.4 AI Engineering Quality

| ID | Mandatory | Trạng thái | Đánh giá |
|---|:---:|---|---|
| AI-AQ.1 | Có | **Đạt có điều kiện** | Chat thật sự retrieve và gọi LLM trên input thật. Khi API lỗi có rule-based fallback; demo phải hiển thị model/backend/run trace để tránh nhầm fallback. Signature vẫn là demo nhưng ngoài AI chat criterion. |
| AI-AQ.2 | Không | **Đạt** | Có custom legal parsing, graph ontology tám tầng, chunking, multi-backend retrieval, graph expansion, grounded prompt và citation; không phải plain API call. |
| AI-AQ.3 | Không | **Chưa đạt** | Không có MLflow/W&B/DVC/model registry. Folder timestamp thiếu Git SHA, dataset/index hash, model revision/checksum, prompt hash, seed, environment và full config. |

### 9.5 Team AI Contribution Evidence

| ID | Mandatory | Trạng thái | Đánh giá |
|---|:---:|---|---|
| AI-TC.1 | Có | **Chưa đạt / không thể chứng minh** | `F:\VlegalAI\.git` không tồn tại; Git root tại ổ đĩa không có commit/remote/tracked project files. Không được tạo commit giả để đối phó rubric. |
| AI-TC.2 | Có | **Chưa đạt** | Không có AUTHORS/CONTRIBUTORS/`AI_CONTRIBUTIONS.md`; README không map thành viên tới dataset, retrieval, graph, model hay evaluation. |

## 10. Kết quả thực nghiệm hiện có

Nguồn: `storage/eval/ragas_notebook/20260702-082502/comparison_exact.csv`.

| Backend | N | Top-k | Hit rate | Precision | Recall | MRR | Avg latency (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| RAG / Qdrant | 1.000 | 10 | 0,5700 | 0,0643 | 0,5150 | 0,4043 | 7,3033 |
| GraphRAG / Neo4j | 1.000 | 10 | 0,2460 | 0,0256 | 0,2325 | 0,1723 | 5,5081 |

GraphRAG giảm 32,4 điểm phần trăm hit rate, 28,25 điểm phần trăm recall và khoảng 57,4% MRR tương đối so với RAG. GraphRAG nhanh hơn khoảng 24,6% trong artifact này nhưng chất lượng retrieval thấp hơn rõ rệt. Không có dòng kết quả HybridRAG, nên chưa thể kết luận fusion mục tiêu cải thiện hay không.

### 10.1 Failure modes theo loại câu hỏi

| Loại | N | RAG hit@10 | GraphRAG hit@10 | Nhận định |
|---|---:|---:|---:|---|
| graph_entity | 150 | 27,33% | 37,33% | Nhóm duy nhất GraphRAG tốt hơn RAG. |
| graph_relation | 150 | 38,67% | 30,00% | Quan hệ graph chưa tạo lợi thế. |
| multi_hop | 200 | 58,00% | 12,00% | Lỗi nghiêm trọng ở mục tiêu cốt lõi GraphRAG. |
| comparison | 80 | 83,75% | 16,25% | Mất nhiều context cần so sánh. |
| temporal_validity | 60 | 60,00% | 0,00% | Chưa xử lý hiệu lực/thời gian. |
| insufficient_context | 20 | 45,00% | 0,00% | Chưa có threshold từ chối/thiếu căn cứ. |

Nguyên nhân cần kiểm chứng bằng ablation:

- Graph extraction tạo một số relation sai ngữ nghĩa và có typo.
- Neo4j dùng full-text + weight thủ công nhưng thiếu semantic vector candidate độc lập.
- Qdrant đang index feature hash, không phải learned semantic embedding.
- Relation weights bị hard-code/lặp và chưa tune trên validation set.
- Dataset bias: hai tài liệu chiếm 80% context.
- Thiếu reranker, effectivity filter, citation validator và insufficient-context threshold.
- Hybrid target chưa có independent branch result, contribution trace và fusion benchmark.

[[PAGE_BREAK]]

## 11. Bảo mật và quyền riêng tư

### P0 — Xử lý ngay

1. Revoke và tạo lại Google service-account key trong `env.json`.
2. Rotate Groq, Qdrant, Neo4j, ngrok và mọi token trong `.env`.
3. Xóa secret khỏi working tree/lịch sử Git thực sau khi repository được khôi phục; history rewrite nếu từng commit.
4. Thêm `.gitignore` cho `.env`, `env.json`, credential JSON, virtualenv, `node_modules`, log, SQLite WAL/SHM và artifact nhạy cảm.
5. Dùng secret manager/CI secret; `.env.example` chỉ chứa placeholder và path tương đối.

Không lặp lại bất kỳ giá trị secret nào trong báo cáo. Do private key đã xuất hiện trong output audit nội bộ, phải coi là compromised ngay cả khi chưa chứng minh từng commit.

### P1 — Trước demo/deploy công khai

- Authentication/authorization, rate limit, request-size limit và CORS allowlist.
- Timeout, retry/backoff, circuit breaker, quota/cost monitoring cho LLM/Qdrant/Neo4j.
- Consent, privacy notice, retention và PII redaction trước khi gửi hợp đồng/hồ sơ tới dịch vụ ngoài.
- Structured logging, correlation/run ID và secret redaction; không trả raw exception cho client.
- Model banner/trace hiển thị đúng DeepSeek 7B revision hoặc báo rõ model thực đang chạy.

## 12. Lộ trình khắc phục ưu tiên

| Ưu tiên | Hành động | Tiêu chí | Điều kiện hoàn tất |
|---|---|---|---|
| P0 | Rotate/revoke secret, thêm ignore/secret manager | P5.1, P6.3 | Secret scan sạch; khóa cũ thu hồi; app dùng secret injection |
| P0 | Khôi phục đúng GitHub clone/lịch sử | AI-TC.1–2 | Remote/commit/PR thật; `AI_CONTRIBUTIONS.md` map người–commit–deliverable |
| P0 | Đồng bộ production model với DeepSeek 7B | D2, P5.3, AI-MI.4, AI-AQ.1 | Adapter/config chỉ định model ID/revision/checksum; runtime trace và smoke test xác nhận |
| P0 | Xóa Local khỏi product contract | D2.1–2, P6.3 | UI/OpenAPI/config chỉ có RAG, GRAPHRAG, HYBRID_RAG; SQLite chỉ internal staging |
| P0 | Triển khai true Hybrid two-branch fusion | D2.2, P7.2–4 | Hai branch độc lập, same index version, fusion contribution trace, no silent fallback |
| P0 | Sửa graph extraction/relation/typo và rebuild | P7.2–4, AI-ER.4 | Unit tests relation; smoke query đúng chủ thể; index version mới |
| P1 | Hoàn thiện architecture views | D2.1–4 | C4, deployment, process/sequence, package/component, versioned OpenAPI |
| P1 | Materialize ERD cần persistence | D3.2, P6.5 | PostgreSQL/migration/FK/constraint cho version/run/contract/eval; cross-store checksum |
| P1 | Class/state/screen design | D3.3–5 | Class/control-flow, state machine, screen spec/flow được version hóa |
| P1 | Chốt dataset protocol | AI-DP, AI-ER.3 | Generator/provenance/license/checksum, frozen split, annotation guideline/reviewer log |
| P1 | Benchmark đầy đủ | AI-ER.1–4, P7.4 | RAG, GraphRAG, HybridRAG, semantic/reranker ablation; RAGAS + error taxonomy |
| P1 | Training requirement | AI-MI.1–3 | Fine-tune embedding/reranker với config/seed/checkpoint hoặc ngoại lệ chính thức |
| P1 | Experiment tracking | AI-AQ.3 | MLflow/W&B hoặc immutable run manifest pin git/dataset/index/model/prompt/env/metric |
| P2 | Refactor/hardening | P5.2–P6.5 | Typed retriever interface, DI, service/repository, async I/O, lock/lint/test/CI |
| P2 | Hoàn thiện UX | D3.3 | History/login/sign flow, mobile overlap, focus/error/accessibility regression tests |

## 13. Gói bằng chứng cho buổi chấm

- `docs/design/VLegalAI_ERD.md` và toàn bộ `docs/design/mermaid/*.mmd`.
- DOCX này với ERD render, data dictionary, mapping và checklist 38 tiêu chí.
- `docs/architecture/`: C4, deployment, component/package, activity/sequence/dataflow đúng AS-IS.
- `docs/ai/`: dataset card, split manifest, annotation guideline, DeepSeek model card, evaluation/error report.
- `experiments/<run-id>/run_manifest.json`: Git SHA, dataset/index hash, DeepSeek revision/checksum, prompt/config/env/seed/metrics/artifacts.
- Demo input mới qua RAG, GraphRAG, HybridRAG; hiển thị branch/fusion/citation/model trace; Local không xuất hiện.
- GitHub Insights/PR/commit chứng minh đóng góp AI từ nhiều thành viên.
- Security evidence: secret scan, key rotation record, privacy/external-service data flow.

## 14. Kết luận cuối

VLegalAI có custom engineering đáng kể: legal parsing, graph ontology tám tầng, multi-backend retrieval, grounded prompt, citation, UI và bộ đánh giá 1.000 mẫu. Báo cáo v2 đã hoàn thiện logical ERD mục tiêu, pin DeepSeek 7B và định nghĩa rõ ba mode; HybridRAG được mô hình hóa đúng là fusion của RAG và GraphRAG, không có Local mode.

Artifact thiết kế giúp D3.1 đạt về Logical Design và bổ sung Physical Database Design/DDL cho user-chat, nhưng không che lấp khoảng trống triển khai. Production source vẫn dùng Groq/default Llama, còn Local fallback và hybrid implementation chưa khớp contract; PostgreSQL migration chưa apply, state machine, model training, experiment tracking và Git contribution vẫn thiếu. Ưu tiên trước buổi chấm là xử lý secret/Git, đồng bộ DeepSeek và ba-mode contract, triển khai true Hybrid fusion, chạy lại benchmark và materialize các entity cần auditability.

## Phụ lục A — Artifact Mermaid

| Artifact | Mục đích |
|---|---|
| `system_overview.mmd` | Ba mode, hai branch, Qdrant/Neo4j, DeepSeek 7B, không Local |
| `knowledge_index_erd.mmd` | Full entity/attribute ERD cho legal document, graph tám tầng, chunk/index |
| `runtime_hybrid_erd.mmd` | Full entity/attribute ERD cho chat, branch/fusion, generation, contract/signature |
| `evaluation_mlops_erd.mmd` | Full entity/attribute ERD cho dataset, experiment, metric, error/artifact |
| `*_overview.mmd` | View rút gọn dùng để render rõ trong DOCX |

## Phụ lục B — Giới hạn audit

- Không có URL/remote GitHub nên không kiểm tra server-side PR, branch protection hoặc contributor stats.
- Không pentest/load test; runtime check chỉ xác nhận UI/API/retrieval/inference prototype.
- Không xác nhận hiệu lực pháp lý của từng văn bản; audit tập trung software/AI engineering.
- Các trạng thái N/A cần hội đồng chấp thuận; nếu chấm literal có thể chuyển thành Chưa đạt.
- Model DeepSeek 7B và three-mode architecture được ghi nhận là target do nhóm xác nhận; runtime conformance chỉ được công nhận sau khi source/config/run artifact được đồng bộ.
