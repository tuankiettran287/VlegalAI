# Backend Low-Level Architecture

This document describes the implementation structure of the VLegal AI backend.

## 1. Runtime topology

```text
Browser
  -> Cloud Run web service (one `vlegal-app` image)
       -> React static files
       -> FastAPI application (`app.main:app`)
            -> PostgreSQL / pgvector (Cloud SQL)
            -> Neo4j graph database (for example, Aura)
            -> Vertex AI (Gemini generation and embeddings)
            -> Tavily and Google Search grounding

The same image also runs as:
  - Cloud Run Worker Pool: Celery worker and Celery beat
  - Cloud Run Job: Alembic migration
  - Cloud Run Job: legal-corpus reindex
```

FastAPI starts shared services during its lifespan and stores them in `app.state`:
`ai`, `tavily`, `google_search`, `indexer`, `retrieval`, `freshness`,
`conversation_memory`, `semantic_answer_cache`, and `article_research`.

## 2. Application modules

| Module | Responsibility |
|---|---|
| `app/main.py` | FastAPI application factory, lifespan, CORS/gzip middleware, request IDs, security headers, exception mapping, SPA serving. |
| `app/api.py` | HTTP API orchestration: chat, contracts, conversations, artifacts, laws, articles, signatures, feedback, health. |
| `app/auth.py` | Google OIDC Authorization Code + PKCE flow, session cookie, current-user and role dependencies. |
| `app/db.py` | Async SQLAlchemy engine, session factory and per-request transaction handling. |
| `app/models.py` | SQLAlchemy domain schema and database constraints/indexes. |
| `app/services/retrieval.py` | Query classification, Hybrid GraphRAG orchestration, context construction and citation-source selection. |
| `app/services/freshness.py` | Legal-source verification, status/replacement detection and verification reports. |
| `app/services/indexer.py` | Official-source ingestion, chunking, embedding generation and PostgreSQL/Neo4j synchronization. |
| `app/services/ai.py` | Gemini prompts, generation calls, data handling and citation validation. |
| `app/services/embeddings.py` | Vertex embedding client/configuration and vector normalization. |
| `app/services/conversation_memory.py` | Incremental summary generation and semantic memory retrieval. |
| `app/services/semantic_cache.py` | Scoped answer cache, vector lookup, law fingerprint validation and expiry. |
| `app/worker.py` | Celery tasks and scheduled corpus/article work. |
| `app/core/security.py` | AES-256-GCM encryption/decryption helpers. |
| `app/core/observability.py` | Request-ID context and structured progress logging. |

## 3. HTTP request pipeline

```text
Request
  -> request-context middleware
       1. validate or create X-Request-ID
       2. bind request ID to logging context
       3. acquire application concurrency semaphore
       4. call route handler
       5. emit timing/progress log and response headers
  -> route dependency resolution
       -> optional/required authenticated user
       -> async database session where needed
  -> service orchestration
  -> typed response schema
```

The application enables CORS only for configured origins, gzip for responses of at
least 1 KB, and response security headers including `X-Content-Type-Options`,
`Referrer-Policy`, and `Permissions-Policy`. Known Gemini, Tavily, and article
research failures are returned as controlled `503` API errors with the request ID.

## 4. API surface

All application endpoints use the configured API prefix (normally `/api`).

| Area | Important endpoints |
|---|---|
| Health | `GET /health/live`, `GET /health/ready` |
| Authentication | `GET /auth/google/login`, `GET /auth/google/callback`, `POST /auth/logout`, `GET /auth/me`, `PATCH /auth/profile` |
| Chat | `POST /chat`, conversation CRUD, conversation-message update/regeneration, answer feedback |
| Legal corpus | `GET /laws`, `GET /laws/detail` |
| Contracts | `POST /contracts/extract`, `/contracts/draft`, `/contracts/review`, `/contracts/compare` |
| User documents | Artifact CRUD and `POST /signatures/prepare` |
| Publishing | Article CRUD and `POST /articles/web-search` |
| Support | `POST /feedback`, `GET /stats`, `GET /templates` |

## 5. Legal chat sequence

```text
POST /api/chat
  -> authenticate optionally; enforce guest distributed rate limit
  -> validate text/attachments and determine chat policy
  -> use exact cache hit when allowed
  -> embed query with Vertex AI `gemini-embedding-001` (1024 dimensions)
  -> use similar cache result only as a draft when allowed
  -> retrieve legal evidence
       -> PostgreSQL/pgvector semantic retrieval
       -> Neo4j relationship expansion
       -> select and compact context sources
  -> optionally search Tavily and Google Search grounding
  -> verify cited source freshness and replacement status
       -> if replacement is found: index official replacement and retrieve again
  -> Gemini 2.5 Flash generates answer from constrained evidence context
  -> validate source citations and evidence relevance
  -> persist encrypted messages/memory only for signed-in users
  -> return answer, sources, and verification report
```

The retriever chooses the available store in this order:

```text
Neo4j + PostgreSQL hybrid -> PostgreSQL -> Neo4j -> local SQLite/FTS5 GraphRAG store
```

The fallback makes legal retrieval resilient to loss of managed graph or relational
services, although the API can indicate degraded/offline operation to the UI.

## 6. Ingestion and freshness flow

```text
Official legal URL / corpus document
  -> LegalIndexer
       -> parse document structure and split into legal chunks
       -> create retrieval-document embeddings using Vertex AI
       -> upsert document/version/chunk records in PostgreSQL
       -> synchronize graph nodes and ontology relationships in Neo4j
       -> record source checksum, version and verification state
```

`LegalFreshnessService` obtains candidate evidence through Tavily and Google
Search grounding, classifies whether a document is active, amended, expired, or
replaced, and produces the verification data returned by the chat API. A discovered
replacement is reindexed before the final answer is generated.

The graph vocabulary is data-driven in `app/legal_ontology.py`; relationship labels
and retrieval weights propagate to the graph integration from that ontology.

## 7. Persistent data model

| Aggregate | Tables/entities | Notes |
|---|---|---|
| Identity | `app_user`, `sso_identity` | Google issuer/subject identity maps to one user. |
| Conversation | `conversation`, `chat_message`, `conversation_summary`, `chat_answer_feedback` | Message ordering is unique per conversation. Content/summary fields are encrypted. Summary vectors use an HNSW cosine index. |
| Legal knowledge | `legal_document`, `legal_chunk` | Document codes are normalized and unique; chunks are versioned and ordered. Graph representation resides in Neo4j. |
| Answer cache | `legal_answer_cache` | Scoped by user/session hash, query hash, expiry, model/prompt revision, and law fingerprint. Query embeddings use HNSW cosine search. |
| Abuse control | `guest_rate_limit` | Counter is keyed by subject hash, window type, and window start so limits work across API replicas. |
| User content | `artifact`, `signature_packet`, `article`, `user_feedback` | Contract/artifact/signature sensitive content is encrypted before PostgreSQL storage. |

The database layer uses SQLAlchemy async sessions and the `postgresql+asyncpg`
driver. `pool_pre_ping`, pool recycling, configurable pool limits, and rollback on
request errors guard database connections and transactions.

## 8. Memory and caching

For an authenticated conversation, recent messages form short-term context. After
turns, Gemini creates an incremental summary; the summary is encrypted and embedded
for durable semantic memory. On a future turn the summary plus recent messages are
used to rebuild conversation context.

The semantic answer cache is deliberately isolated by scope (user or guest
session). Exact normalized queries can return cached answers after validating the
legal-source fingerprint. Similar queries use the cache as drafting context but
still run retrieval and generate an adjusted answer. Personal/contextual requests
do not use the shared response path.

## 9. Asynchronous processing

`app/worker.py` configures Celery with PostgreSQL-derived broker/result URLs. The
worker uses late acknowledgements and a prefetch multiplier of one. Celery beat
schedules:

- legal-corpus verification every 10 days;
- article-research/publishing at configured daily hours.

The corpus task loads legal documents ordered by oldest verification time and runs
freshness checks. Reindexing occurs only when a replacement/update is discovered.

## 10. Security and operational boundaries

- Browser code has no model-provider keys, retriever settings, or service-account credentials.
- Cloud Run uses Application Default Credentials/service identity for Vertex AI; local environments may mount a credential file read-only.
- Secrets are supplied through environment configuration or Secret Manager and are not copied into the application image.
- Session cookies are HttpOnly; authorization dependencies protect user-owned resources and privileged operations.
- `GEMINI_DATA_POLICY=redact` redacts common personally identifying and secret values before sending text to external AI/search providers.
- `GET /health/ready` verifies critical dependencies/configuration; `GET /health/live` supports process liveness checks.

## 11. Deployment dependencies

```text
Cloud Run service   -> Cloud SQL + Neo4j Aura + Vertex AI + Tavily
Cloud Run worker    -> Cloud SQL + Neo4j Aura + Vertex AI + Tavily
Migration job       -> Cloud SQL
Reindex job         -> corpus mount/bucket + Cloud SQL + Neo4j Aura + Vertex AI
```

The web service, worker, beat, migration, and reindex roles are pinned to the same
container image for a commit. Migration must complete before API and worker
processes begin serving work.
