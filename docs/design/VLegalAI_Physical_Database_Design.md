# VLegalAI Physical Database Design

**Phiên bản:** 1.0  
**Ngày:** 13/07/2026  
**Mục tiêu:** Materialization specification cho identity, hội thoại và trace retrieval  
**Target DBMS:** PostgreSQL 16+  
**DDL:** `docs/design/sql/V001__runtime_user_privacy.sql`

## 1. Trả lời tiêu chí đánh giá

**Does the Physical Design (Database) represent the materialization of a database into the system?**

**Kết luận:** Có ở mức **thiết kế TO-BE có thể triển khai**, vì tài liệu chỉ rõ table, field, type/size, nullability, default, PK/FK/unique/check/index và mapping về logical design. Tuy nhiên chưa được xem là **đã materialize trong runtime** cho tới khi migration được chạy trên PostgreSQL và có bằng chứng introspection/test. Schema SQLite, Neo4j và Qdrant hiện tại chỉ materialize một phần Knowledge & Index; chưa có durable user/chat database.

## 2. Ranh giới vật lý

| Store | Vai trò | Dữ liệu | Trạng thái |
|---|---|---|---|
| PostgreSQL | System of record | User hash, session/message digest, feedback, runtime trace, metadata | TO-BE; có DDL |
| Neo4j | Graph projection | Legal node/relation/chunk projection | AS-IS một phần |
| Qdrant | Vector projection | Vector và chunk payload | AS-IS một phần |
| SQLite | Build/staging artifact | docs, nodes, edges, chunks, FTS | AS-IS; không phải production user DB |
| Runtime memory | Dữ liệu rõ ngắn hạn | Nội dung câu hỏi/hội thoại cần để sinh câu trả lời | Ephemeral; không persist |

## 3. Chính sách hash bắt buộc

- Không lưu email, tên hiển thị, số điện thoại, tổ chức, feedback text, query hoặc conversation text ở dạng rõ.
- Mật khẩu dùng **Argon2id** với salt riêng cho từng mật khẩu; encoded hash tối đa `VARCHAR(255)`.
- PII và nội dung do user cung cấp dùng **HMAC-SHA-256 có khóa**, lưu dạng hex `CHAR(64)`. Không dùng SHA-256 thuần cho email/điện thoại vì không chống được dictionary attack.
- Khóa HMAC do secret manager quản lý, không lưu trong database. `hash_key_version` chỉ lưu phiên bản khóa.
- `user_id`, role/status và timestamp là định danh/metadata do hệ thống sinh để giữ PK, FK và audit; chúng không phải nội dung nhận dạng do user cung cấp nên không hash.
- `APP_USER.conversation_hash` là rolling digest tùy chọn của lịch sử; `RAG_SESSION.conversation_hash` là digest của transcript có thứ tự; `CHAT_MESSAGE.message_content_hash` là digest từng message.
- Hash là một chiều. Với policy này, database không thể khôi phục lịch sử hội thoại. Nếu nghiệp vụ cần xem lại nội dung, phải có quyết định kiến trúc riêng về mã hóa có thể giải mã; không được gọi mã hóa là hash.

Rolling conversation digest đề xuất:

`H_n = HMAC-SHA-256(key_v, H_(n-1) || session_id || message_role || canonical_message)`

## 4. Danh sách physical table

| Physical table | Logical entity | PK/FK chính | Mục đích | Raw user data |
|---|---|---|---|---|
| `app_user` | `APP_USER` | PK user_id | Identity, authentication hash, profile/conversation digest | Không |
| `rag_session` | `RAG_SESSION` | PK session_id; FK user_id | Nhóm message theo user/session | Không |
| `chat_message` | `CHAT_MESSAGE` | PK message_id; FK session/parent | Audit message bằng digest | Không |
| `retrieval_run` | `RETRIEVAL_RUN` | PK run_id; FK request_message | Trace mode/index/top-k/status | Không |
| `user_feedback` | `USER_FEEDBACK` | PK feedback_id; FK user/session/message | Rating và digest feedback | Không |

## 5. Physical data dictionary — `app_user`

| Field | PostgreSQL type / size | Null / default | Key / constraint | Logical mapping |
|---|---|---|---|---|
| `user_id` | `UUID` / 16 bytes | NOT NULL / `gen_random_uuid()` | PK | `APP_USER.user_id` |
| `email_hash` | `CHAR(64)` | NOT NULL / none | UNIQUE; lowercase hex | `APP_USER.email` → hash |
| `display_name_hash` | `CHAR(64)` | NOT NULL / none | lowercase hex | `APP_USER.display_name` → hash |
| `phone_hash` | `CHAR(64)` | NULL / `NULL` | lowercase hex khi có | `APP_USER.phone` → hash |
| `organization_hash` | `CHAR(64)` | NULL / `NULL` | lowercase hex khi có | `APP_USER.organization` → hash |
| `password_hash` | `VARCHAR(255)` | NOT NULL / none | phải bắt đầu `$argon2id$` | `APP_USER.password` → salted hash |
| `profile_hash` | `CHAR(64)` | NOT NULL / none | lowercase hex | Digest toàn bộ profile canonical |
| `conversation_hash` | `CHAR(64)` | NULL / `NULL` | lowercase hex khi có | Rolling conversation digest |
| `role_code` | `VARCHAR(32)` | NOT NULL / `'USER'` | USER/REVIEWER/ADMIN | Role hệ thống, không phải PII |
| `account_status` | `VARCHAR(16)` | NOT NULL / `'ACTIVE'` | PENDING/ACTIVE/LOCKED/DISABLED | `APP_USER.account_status` |
| `hash_algorithm` | `VARCHAR(32)` | NOT NULL / `'HMAC-SHA-256'` | fixed enum | Hash policy |
| `hash_key_version` | `SMALLINT` / 2 bytes | NOT NULL / `1` | > 0 | Key rotation metadata |
| `created_at` | `TIMESTAMPTZ` / 8 bytes | NOT NULL / current timestamp | audit | `APP_USER.created_at` |
| `updated_at` | `TIMESTAMPTZ` / 8 bytes | NOT NULL / current timestamp | app updates on mutation | `APP_USER.updated_at` |

## 6. Physical data dictionary — session, message, run và feedback

| Table.field | Type / size | Null / default | Key / constraint | Logical mapping |
|---|---|---|---|---|
| `rag_session.session_id` | `UUID` | NOT NULL / generated | PK | `RAG_SESSION.session_id` |
| `rag_session.user_id` | `UUID` | NOT NULL | FK → app_user; cascade | `RAG_SESSION.user_id` |
| `rag_session.title_hash` | `CHAR(64)` | NULL | hex digest | `RAG_SESSION.title` → hash |
| `rag_session.conversation_hash` | `CHAR(64)` | NOT NULL | hex digest | Transcript digest |
| `rag_session.session_status` | `VARCHAR(16)` | NOT NULL / `'ACTIVE'` | ACTIVE/ARCHIVED/DELETED | `RAG_SESSION.session_status` |
| `rag_session.created_at` | `TIMESTAMPTZ` | NOT NULL / current timestamp | audit | `RAG_SESSION.created_at` |
| `rag_session.last_activity_at` | `TIMESTAMPTZ` | NOT NULL / current timestamp | indexed with user_id | `RAG_SESSION.last_activity_at` |
| `chat_message.message_id` | `UUID` | NOT NULL / generated | PK | `CHAT_MESSAGE.message_id` |
| `chat_message.session_id` | `UUID` | NOT NULL | FK → rag_session; cascade | `CHAT_MESSAGE.session_id` |
| `chat_message.parent_message_id` | `UUID` | NULL | self FK; set null | `CHAT_MESSAGE.parent_message_id` |
| `chat_message.message_role` | `VARCHAR(16)` | NOT NULL | SYSTEM/USER/ASSISTANT/TOOL | `CHAT_MESSAGE.message_role` |
| `chat_message.message_content_hash` | `CHAR(64)` | NOT NULL | hex digest | `CHAT_MESSAGE.message_content` → hash |
| `chat_message.message_status` | `VARCHAR(16)` | NOT NULL / `'COMPLETED'` | controlled values | `CHAT_MESSAGE.message_status` |
| `chat_message.token_count` | `INTEGER` / 4 bytes | NOT NULL / `0` | >= 0 | Token audit |
| `chat_message.created_at` | `TIMESTAMPTZ` | NOT NULL / current timestamp | indexed with session_id | `CHAT_MESSAGE.created_at` |
| `retrieval_run.retrieval_run_id` | `UUID` | NOT NULL / generated | PK | `RETRIEVAL_RUN.retrieval_run_id` |
| `retrieval_run.request_message_id` | `UUID` | NOT NULL | FK → chat_message; restrict | `RETRIEVAL_RUN.request_message_id` |
| `retrieval_run.index_version_id` | `UUID` | NOT NULL | logical FK to index registry | `RETRIEVAL_RUN.index_version_id` |
| `retrieval_run.retrieval_mode` | `VARCHAR(16)` | NOT NULL | RAG/GRAPHRAG/HYBRID_RAG | `RETRIEVAL_RUN.retrieval_mode` |
| `retrieval_run.normalized_query_hash` | `CHAR(64)` | NOT NULL | hex digest | `normalized_query` → hash |
| `retrieval_run.requested_top_k` | `SMALLINT` | NOT NULL / `10` | 1–100 | Requested top-k |
| `retrieval_run.final_top_k` | `SMALLINT` | NULL | 0–requested top-k | Final hit count |
| `retrieval_run.run_status` | `VARCHAR(16)` | NOT NULL / `'PENDING'` | controlled values | `RETRIEVAL_RUN.run_status` |
| `user_feedback.feedback_id` | `UUID` | NOT NULL / generated | PK | `USER_FEEDBACK.feedback_id` |
| `user_feedback.user_id` | `UUID` | NOT NULL | FK → app_user; cascade | `USER_FEEDBACK.user_id` |
| `user_feedback.session_id` | `UUID` | NULL | FK → rag_session; set null | `USER_FEEDBACK.session_id` |
| `user_feedback.message_id` | `UUID` | NULL | FK → chat_message; set null | `USER_FEEDBACK.message_id` |
| `user_feedback.rating` | `SMALLINT` | NOT NULL | 1–5 | `USER_FEEDBACK.rating` |
| `user_feedback.category` | `VARCHAR(32)` | NULL | controlled by application | `USER_FEEDBACK.category` |
| `user_feedback.comment_hash` | `CHAR(64)` | NULL | hex digest | `comment_text` → hash |
| `user_feedback.page_hash` | `CHAR(64)` | NULL | hex digest | `page` → hash |
| `user_feedback.created_at` | `TIMESTAMPTZ` | NOT NULL / current timestamp | audit/index | `USER_FEEDBACK.created_at` |

## 7. Logical-to-physical mapping tổng thể

| Logical object | Physical materialization | Mức độ |
|---|---|---|
| `APP_USER` | PostgreSQL `app_user` | TO-BE DDL hoàn chỉnh; chưa deploy |
| `RAG_SESSION` | PostgreSQL `rag_session` | TO-BE DDL hoàn chỉnh; chưa deploy |
| `CHAT_MESSAGE` | PostgreSQL `chat_message` | TO-BE DDL hoàn chỉnh; hash-only |
| `USER_FEEDBACK` | PostgreSQL `user_feedback` | TO-BE DDL hoàn chỉnh; hash-only |
| `RETRIEVAL_RUN` | PostgreSQL `retrieval_run` | TO-BE phần core; branch/hit/fusion bổ sung ở migration sau |
| `LEGAL_DOCUMENT` | SQLite `docs` / documents.jsonl | AS-IS một phần; document/version bị gộp |
| `KNOWLEDGE_NODE` | SQLite `nodes`; Neo4j `LegalNode` | AS-IS một phần |
| `KNOWLEDGE_RELATION` | SQLite `edges`; Neo4j relationship | AS-IS một phần |
| `TEXT_CHUNK` | SQLite `chunks`; Neo4j `LegalChunk`; Qdrant payload | AS-IS một phần |
| `CHUNK_EMBEDDING` | SQLite BLOB; Qdrant vector 1536/cosine | AS-IS một phần; thiếu model provenance |
| `INDEX_VERSION` | Chưa có physical registry | Chưa materialize |

## 8. Index, integrity và retention

- `email_hash` unique để lookup tài khoản mà không lưu email rõ.
- Composite index `rag_session(user_id, last_activity_at DESC)` phục vụ danh sách session.
- Composite index `chat_message(session_id, created_at)` phục vụ audit chuỗi digest.
- Tất cả relationship user/session/message dùng FK với delete rule rõ ràng.
- Hex hash có `CHECK` đúng 64 ký tự; enum/status/rating/top-k/time đều có `CHECK`.
- Raw conversation chỉ được giữ trong bộ nhớ trong thời gian xử lý và phải xóa sau response hoặc theo TTL được phê duyệt.
- Log/APM/error trace không được ghi raw PII, prompt hoặc conversation content.

## 9. Checklist chứng minh materialization

| Kiểm tra | Design evidence | Runtime evidence bắt buộc | Trạng thái hiện tại |
|---|---|---|---|
| Table list đầy đủ | Section 4 + DDL | `information_schema.tables` | Thiết kế đạt; runtime chưa |
| Field/type/size | Sections 5–6 | `information_schema.columns` | Thiết kế đạt; runtime chưa |
| Null/default | Sections 5–6 + DDL | column default/nullability query | Thiết kế đạt; runtime chưa |
| PK/FK/unique/check | DDL constraints | `pg_constraint` | Thiết kế đạt; runtime chưa |
| Index | DDL index statements | `pg_indexes` + query plan | Thiết kế đạt; runtime chưa |
| Logical mapping | Section 7 | Traceability review | Đạt ở tài liệu |
| Hash-only user data | Sections 3, 5, 6 | negative tests + DB scan | Thiết kế đạt; runtime chưa |
| Migration/version | File `V001__...sql` | migration history/checksum | File có; chưa apply |
| CRUD/integration | Không thuộc static design | automated integration tests | Chưa có |

## 10. Acceptance rule

Chỉ đánh dấu tiêu chí **“Physical Design materialized into system — Đạt”** khi đồng thời có:

1. Migration `V001` chạy thành công trên PostgreSQL target.
2. Introspection khớp 100% table/field/type/default/constraint/index trong tài liệu.
3. Test chứng minh raw email/name/phone/password/query/message/feedback không xuất hiện trong DB, log hoặc backup.
4. FK, unique, check và delete behavior có negative test.
5. Logical-to-physical mapping được review và ký xác nhận.

Trước các bằng chứng trên, trạng thái trung thực là **“Một phần — physical design complete, runtime materialization pending.”**
