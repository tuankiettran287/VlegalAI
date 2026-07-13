-- VLegalAI physical database design - runtime identity/chat privacy baseline.
-- Target: PostgreSQL 16+
-- Important: the database stores no raw user PII or raw conversation content.
-- PII/content digests are computed in the application with keyed HMAC-SHA-256
-- after canonicalization. Passwords use an encoded Argon2id hash with a unique salt.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE app_user (
    user_id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    email_hash            CHAR(64)     NOT NULL UNIQUE,
    display_name_hash     CHAR(64)     NOT NULL,
    phone_hash            CHAR(64),
    organization_hash     CHAR(64),
    password_hash         VARCHAR(255) NOT NULL,
    profile_hash          CHAR(64)     NOT NULL,
    conversation_hash     CHAR(64),
    role_code             VARCHAR(32)  NOT NULL DEFAULT 'USER',
    account_status        VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
    hash_algorithm        VARCHAR(32)  NOT NULL DEFAULT 'HMAC-SHA-256',
    hash_key_version      SMALLINT     NOT NULL DEFAULT 1,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT ck_app_user_email_hash
        CHECK (email_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_app_user_display_name_hash
        CHECK (display_name_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_app_user_phone_hash
        CHECK (phone_hash IS NULL OR phone_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_app_user_organization_hash
        CHECK (organization_hash IS NULL OR organization_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_app_user_profile_hash
        CHECK (profile_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_app_user_conversation_hash
        CHECK (conversation_hash IS NULL OR conversation_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_app_user_password_hash
        CHECK (password_hash LIKE '$argon2id$%'),
    CONSTRAINT ck_app_user_role
        CHECK (role_code IN ('USER', 'REVIEWER', 'ADMIN')),
    CONSTRAINT ck_app_user_status
        CHECK (account_status IN ('PENDING', 'ACTIVE', 'LOCKED', 'DISABLED')),
    CONSTRAINT ck_app_user_hash_algorithm
        CHECK (hash_algorithm = 'HMAC-SHA-256'),
    CONSTRAINT ck_app_user_hash_key_version
        CHECK (hash_key_version > 0)
);

CREATE TABLE rag_session (
    session_id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID         NOT NULL,
    title_hash            CHAR(64),
    conversation_hash     CHAR(64)     NOT NULL,
    session_status        VARCHAR(16)  NOT NULL DEFAULT 'ACTIVE',
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_activity_at      TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_rag_session_user
        FOREIGN KEY (user_id) REFERENCES app_user(user_id) ON DELETE CASCADE,
    CONSTRAINT ck_rag_session_title_hash
        CHECK (title_hash IS NULL OR title_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_rag_session_conversation_hash
        CHECK (conversation_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_rag_session_status
        CHECK (session_status IN ('ACTIVE', 'ARCHIVED', 'DELETED'))
);

CREATE INDEX idx_rag_session_user_activity
    ON rag_session(user_id, last_activity_at DESC);

CREATE TABLE chat_message (
    message_id            UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id            UUID         NOT NULL,
    parent_message_id     UUID,
    message_role          VARCHAR(16)  NOT NULL,
    message_content_hash  CHAR(64)     NOT NULL,
    message_status        VARCHAR(16)  NOT NULL DEFAULT 'COMPLETED',
    token_count           INTEGER      NOT NULL DEFAULT 0,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_chat_message_session
        FOREIGN KEY (session_id) REFERENCES rag_session(session_id) ON DELETE CASCADE,
    CONSTRAINT fk_chat_message_parent
        FOREIGN KEY (parent_message_id) REFERENCES chat_message(message_id) ON DELETE SET NULL,
    CONSTRAINT ck_chat_message_role
        CHECK (message_role IN ('SYSTEM', 'USER', 'ASSISTANT', 'TOOL')),
    CONSTRAINT ck_chat_message_content_hash
        CHECK (message_content_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_chat_message_status
        CHECK (message_status IN ('PENDING', 'COMPLETED', 'FAILED', 'REDACTED')),
    CONSTRAINT ck_chat_message_token_count
        CHECK (token_count >= 0)
);

CREATE INDEX idx_chat_message_session_created
    ON chat_message(session_id, created_at);

CREATE TABLE retrieval_run (
    retrieval_run_id      UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    request_message_id    UUID         NOT NULL,
    index_version_id      UUID         NOT NULL,
    retrieval_mode        VARCHAR(16)  NOT NULL,
    normalized_query_hash CHAR(64)     NOT NULL,
    requested_top_k       SMALLINT     NOT NULL DEFAULT 10,
    final_top_k           SMALLINT,
    run_status            VARCHAR(16)  NOT NULL DEFAULT 'PENDING',
    started_at            TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at           TIMESTAMPTZ,

    CONSTRAINT fk_retrieval_run_request_message
        FOREIGN KEY (request_message_id) REFERENCES chat_message(message_id) ON DELETE RESTRICT,
    CONSTRAINT ck_retrieval_run_mode
        CHECK (retrieval_mode IN ('RAG', 'GRAPHRAG', 'HYBRID_RAG')),
    CONSTRAINT ck_retrieval_run_query_hash
        CHECK (normalized_query_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_retrieval_run_requested_top_k
        CHECK (requested_top_k BETWEEN 1 AND 100),
    CONSTRAINT ck_retrieval_run_final_top_k
        CHECK (final_top_k IS NULL OR final_top_k BETWEEN 0 AND requested_top_k),
    CONSTRAINT ck_retrieval_run_status
        CHECK (run_status IN ('PENDING', 'RUNNING', 'SUCCEEDED', 'FAILED', 'CANCELLED')),
    CONSTRAINT ck_retrieval_run_time
        CHECK (finished_at IS NULL OR finished_at >= started_at)
);

CREATE INDEX idx_retrieval_run_message
    ON retrieval_run(request_message_id);

CREATE TABLE user_feedback (
    feedback_id           UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               UUID         NOT NULL,
    session_id            UUID,
    message_id            UUID,
    rating                SMALLINT     NOT NULL,
    category              VARCHAR(32),
    comment_hash          CHAR(64),
    page_hash             CHAR(64),
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_user_feedback_user
        FOREIGN KEY (user_id) REFERENCES app_user(user_id) ON DELETE CASCADE,
    CONSTRAINT fk_user_feedback_session
        FOREIGN KEY (session_id) REFERENCES rag_session(session_id) ON DELETE SET NULL,
    CONSTRAINT fk_user_feedback_message
        FOREIGN KEY (message_id) REFERENCES chat_message(message_id) ON DELETE SET NULL,
    CONSTRAINT ck_user_feedback_rating
        CHECK (rating BETWEEN 1 AND 5),
    CONSTRAINT ck_user_feedback_comment_hash
        CHECK (comment_hash IS NULL OR comment_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_user_feedback_page_hash
        CHECK (page_hash IS NULL OR page_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX idx_user_feedback_user_created
    ON user_feedback(user_id, created_at DESC);

COMMENT ON COLUMN app_user.email_hash IS
    'Lowercase/trim/canonicalize email, then HMAC-SHA-256; never store raw email.';
COMMENT ON COLUMN app_user.password_hash IS
    'Encoded Argon2id hash including parameters and unique salt; never reversible.';
COMMENT ON COLUMN app_user.conversation_hash IS
    'Optional rolling digest of the user conversation history; contains no conversation text.';
COMMENT ON COLUMN rag_session.conversation_hash IS
    'Digest of the ordered session transcript for integrity/audit only.';
COMMENT ON COLUMN chat_message.message_content_hash IS
    'HMAC-SHA-256 digest of canonicalized message content; raw content is runtime-only.';

