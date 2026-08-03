from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration loaded once per process.

    Retrieval and model choices intentionally live only on the server.  The
    public UI never receives provider keys or a backend selector.
    """

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "VLegal AI"
    app_env: Literal["development", "test", "staging", "production"] = "development"
    api_prefix: str = "/api"
    public_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    frontend_dist_dir: str = ""
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:5173"])
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://vlegal:vlegal@postgres:5432/vlegal"
    database_pool_size: int = 20
    database_max_overflow: int = 40
    database_pool_timeout: int = 30
    session_secret: str = "replace-with-at-least-32-random-characters"
    session_ttl_seconds: int = 8 * 60 * 60
    cookie_secure: bool = False
    guest_chat_requests_per_minute: int = 4
    guest_chat_requests_per_hour: int = 30
    conversation_summary_batch_size: int = Field(default=12, ge=2, le=40)
    conversation_summary_max_tokens: int = Field(default=900, ge=128, le=2400)
    semantic_answer_cache_enabled: bool = True
    semantic_answer_cache_similarity: float = Field(default=0.96, ge=0.8, le=1)
    semantic_answer_cache_ttl_hours: int = Field(default=24, ge=1, le=168)
    semantic_answer_cache_max_query_chars: int = Field(default=1500, ge=100, le=5000)
    oidc_issuer: str = "https://accounts.google.com"
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = ""
    oidc_scopes: str = "openid email profile"
    oidc_admin_groups: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["vlegal-admins"])
    oidc_reviewer_groups: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["vlegal-reviewers"])

    message_encryption_key: str = ""

    retriever_backend: Literal["rag", "graphrag", "hybrid_rag", "local_graphrag"] = "hybrid_rag"
    retrieval_top_k: int = Field(default=10, ge=1, le=64)
    legal_freshness_ttl_hours: int = Field(default=24, ge=0, le=168)
    legal_verification_concurrency: int = Field(default=8, ge=1, le=32)
    legal_freshness_timeout_seconds: float = Field(default=3.5, ge=1.0, le=300.0)
    tavily_timeout_seconds: float = Field(default=3.5, ge=1.0, le=30.0)
    freshness_lock_wait_seconds: int = Field(default=120, ge=1, le=600)
    require_freshness_check: bool = False
    legal_search_require_both: bool = True
    legal_verdict_min_confidence: float = Field(default=0.75, ge=0.5, le=1)
    max_laws_verified_per_request: int = Field(default=16, ge=1, le=64)
    google_search_max_results: int = Field(default=10, ge=1, le=20)

    # Text generation uses Vertex AI with the service-account credential in
    # env.json. The credential path can be overridden for container/secret
    # mounts without exposing any key to the frontend.
    gemini_credentials_path: str = str(PROJECT_ROOT / "env.json")
    gemini_api_key: str = ""
    gemini_use_adc: bool = False
    gemini_project_id: str = ""
    gemini_location: str = "global"
    gemini_model: str = "gemini-2.5-flash"
    gemini_timeout_seconds: int = Field(default=120, ge=5, le=600)
    gemini_max_retries: int = Field(default=3, ge=1, le=3)
    gemini_max_concurrent_generations: int = Field(default=8, ge=1, le=64)
    gemini_google_search_max_output_tokens: int = Field(
        default=16_384,
        ge=1_024,
        le=65_535,
    )
    gemini_thinking_budget: int = Field(default=0, ge=0, le=24_576)
    gemini_thinking_level: Literal["minimal", "low", "medium", "high"] = "low"
    gemini_data_policy: Literal["redact", "deny", "allow"] = "redact"
    # Route-aware generation timeouts. These bound the Gemini call
    # independently of the lower-level httpx socket timeout so that a stalled
    # model call raises GeminiError (→ fallback) rather than waiting the full
    # gemini_timeout_seconds (120 s by default).
    legal_chat_fast_timeout_seconds: float = Field(default=8.0, ge=2.0, le=60.0)
    legal_chat_generation_timeout_seconds: float = Field(default=30.0, ge=5.0, le=120.0)
    legal_chat_citation_repair_timeout_seconds: float = Field(default=3.5, ge=1.0, le=30.0)
    query_rewrite_enabled: bool = True
    query_rewrite_timeout_seconds: int = Field(default=12, ge=2, le=30)
    query_rewrite_min_confidence: float = Field(default=0.75, ge=0.5, le=1)
    evidence_gate_enabled: bool = True
    evidence_gate_timeout_seconds: float = Field(default=5.0, ge=1.0, le=20.0)
    evidence_gate_max_sources: int = Field(default=8, ge=1, le=20)

    # Semantic embeddings can use Vertex AI or the Gemini Developer API. The
    # provider is independent from GEMINI_USE_ADC so generation can remain on
    # Vertex while bulk embedding uses the API-key-backed batch endpoint.
    embedding_provider: Literal["vertex", "gemini-api"] = "vertex"
    embedding_model: str = "gemini-embedding-001"
    embedding_location: str = "global"
    embedding_max_concurrency: int = Field(default=8, ge=1, le=64)
    embedding_batch_size: int = Field(default=20, ge=1, le=100)
    embedding_max_items_per_minute: int = Field(default=0, ge=0, le=100_000)
    embedding_timeout_seconds: int = Field(default=60, ge=5, le=600)
    embedding_max_retries: int = Field(default=3, ge=1, le=10)
    embedding_auto_truncate: bool = True
    embedding_vertex_locations: str = ""
    embedding_vertex_requests_per_minute: float = Field(
        default=0,
        ge=0,
        le=10_000,
    )
    embedding_vertex_max_queue_wait_seconds: float = Field(default=0, ge=0, le=600)

    tavily_api_key: str = ""
    tavily_search_depth: Literal["basic", "advanced"] = "advanced"
    tavily_timeout_seconds: int = 30
    daily_article_enabled: bool = True
    daily_article_topics: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "quyền và nghĩa vụ trong quan hệ lao động",
            "giao kết và thực hiện hợp đồng dân sự",
            "hợp đồng thương mại và quản trị rủi ro",
            "bảo hiểm xã hội và quyền lợi người lao động",
            "nhà ở, đất đai và giao dịch tài sản",
            "thuế và nghĩa vụ tài chính của cá nhân, doanh nghiệp",
            "bảo vệ người tiêu dùng trong giao dịch số",
            "thành lập và quản trị doanh nghiệp",
            "hôn nhân, gia đình và phân chia di sản thừa kế",
            "sở hữu trí tuệ, bản quyền và chuyển giao công nghệ",
            "bảo vệ dữ liệu cá nhân và an ninh mạng",
            "thương mại điện tử và hợp đồng điện tử",
            "giải quyết tranh chấp, tố tụng và trọng tài thương mại",
            "thủ tục hành chính và khiếu nại quyết định hành chính",
            "trách nhiệm hình sự của cá nhân và pháp nhân thương mại",
            "ngân hàng, tín dụng và giao dịch bảo đảm",
            "xây dựng, đấu thầu và quản lý dự án",
            "môi trường và trách nhiệm tuân thủ của doanh nghiệp",
            "y tế, giáo dục và các quyền lợi xã hội",
            "lao động nước ngoài, xuất nhập cảnh và cư trú",
        ]
    )
    official_legal_domains: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: [
            "vanban.chinhphu.vn",
            "vbpl.vn",
            "quochoi.vn",
            "congbao.chinhphu.vn",
            "moj.gov.vn",
        ]
    )

    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    # All pgvector columns and HNSW indexes are currently schema-bound to 1024.
    # Reject a mismatched environment value during startup instead of failing
    # later during inserts or similarity queries.
    postgres_vector_size: int = Field(default=1024, ge=1024, le=1024)
    hybrid_vector_weight: float = Field(default=0.55, ge=0)
    hybrid_bm25_weight: float = Field(default=0.45, ge=0)
    hybrid_rrf_k: int = Field(default=60, ge=1)
    bm25_k1: float = Field(default=1.5, gt=0)
    bm25_b: float = Field(default=0.75, ge=0, le=1)

    legal_data_dir: str = str(PROJECT_ROOT / "Data (1)")
    legal_storage_dir: str = str(PROJECT_ROOT / "storage" / "graphrag")
    legal_graphrag_db: str = str(PROJECT_ROOT / "storage" / "graphrag" / "legal_graphrag.sqlite")

    @field_validator(
        "cors_origins",
        "official_legal_domains",
        "oidc_admin_groups",
        "oidc_reviewer_groups",
        "daily_article_topics",
        mode="before",
    )
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            normalized = value.strip()
            if normalized.startswith("["):
                try:
                    decoded = json.loads(normalized)
                except json.JSONDecodeError:
                    decoded = None
                if isinstance(decoded, list):
                    return [str(part).strip() for part in decoded if str(part).strip()]
            return [part.strip() for part in normalized.split(",") if part.strip()]
        return value

    @field_validator("official_legal_domains", mode="after")
    @classmethod
    def normalize_official_domains(cls, value: list[str]) -> list[str]:
        return [domain.strip().lower().removeprefix("www.") for domain in value if domain.strip()]

    @field_validator("oidc_issuer", mode="after")
    @classmethod
    def google_issuer_only(cls, value: str) -> str:
        normalized = value.rstrip("/")
        if normalized and normalized != "https://accounts.google.com":
            raise ValueError("OIDC_ISSUER must be https://accounts.google.com for Google login")
        return normalized

    @field_validator("retriever_backend", mode="before")
    @classmethod
    def normalize_retriever_backend(cls, value: object) -> str:
        normalized = str(value or "hybrid_rag").strip().lower().replace("-", "_")
        aliases = {
            "auto": "hybrid_rag",
            "hybrid": "hybrid_rag",
            "neo4j_postgres": "hybrid_rag",
            "postgres": "rag",
            "pgvector": "rag",
            "vector": "rag",
            "neo4j": "graphrag",
            "graph": "graphrag",
            "sqlite": "local_graphrag",
            "local": "local_graphrag",
        }
        return aliases.get(normalized, normalized)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def oidc_ready(self) -> bool:
        return bool(
            self.oidc_issuer
            and self.oidc_client_id
            and self.oidc_client_secret
            and self.oidc_callback_url
        )

    @property
    def oidc_callback_url(self) -> str:
        configured = self.oidc_redirect_uri.strip()
        if configured:
            return configured
        api_prefix = self.api_prefix.strip("/")
        return f"{self.public_url.rstrip('/')}/{api_prefix}/auth/google/callback"

    @property
    def gemini_credentials_local_path(self) -> Path:
        credentials_path = Path(self.gemini_credentials_path).expanduser()
        return credentials_path if credentials_path.is_absolute() else PROJECT_ROOT / credentials_path

    @property
    def gemini_ready(self) -> bool:
        if not self.gemini_model.strip():
            return False
        credentials_path = self.gemini_credentials_local_path
        if credentials_path.is_file():
            try:
                payload = json.loads(credentials_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, ValueError):
                return False
            if not isinstance(payload, dict) or payload.get("type") != "service_account":
                return False
            required_fields = ("client_email", "private_key", "token_uri")
            if not all(
                isinstance(payload.get(field), str) and payload[field].strip()
                for field in required_fields
            ):
                return False
            return bool(
                self.gemini_project_id.strip()
                or str(payload.get("project_id") or "").strip()
            )
        return self.gemini_use_adc

    @property
    def embedding_ready(self) -> bool:
        from app.services.embeddings import embedding_config_from_settings

        return embedding_config_from_settings(self).ready

    @property
    def tavily_ready(self) -> bool:
        return bool(self.tavily_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
