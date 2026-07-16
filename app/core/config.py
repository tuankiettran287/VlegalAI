from __future__ import annotations

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
    cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["http://localhost:5173"])
    log_level: str = "INFO"

    database_url: str = "postgresql+asyncpg://vlegal:vlegal@postgres:5432/vlegal"
    database_pool_size: int = 20
    database_max_overflow: int = 40
    database_pool_timeout: int = 30
    redis_url: str = "redis://redis:6379/0"

    session_secret: str = "replace-with-at-least-32-random-characters"
    session_ttl_seconds: int = 8 * 60 * 60
    cookie_secure: bool = False
    guest_chat_requests_per_minute: int = 4
    guest_chat_requests_per_hour: int = 30
    oidc_issuer: str = "https://accounts.google.com"
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_redirect_uri: str = "http://localhost:8000/api/auth/google/callback"
    oidc_scopes: str = "openid email profile"
    oidc_admin_groups: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["vlegal-admins"])
    oidc_reviewer_groups: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["vlegal-reviewers"])

    message_encryption_key: str = ""

    retriever_backend: Literal["rag", "graphrag", "hybrid_rag", "local_graphrag"] = "hybrid_rag"
    retrieval_top_k: int = 10
    legal_freshness_ttl_hours: int = 24
    legal_verification_concurrency: int = 4
    freshness_lock_ttl_seconds: int = 120
    require_freshness_check: bool = True
    max_laws_verified_per_request: int = 16

    # Qwen runs in-process from a checkpoint that already exists on disk.
    # No prompt or legal document is sent to an external model API.
    qwen_model_path: str = str(PROJECT_ROOT / "models" / "Qwen3-4B")
    qwen_model: str = "Qwen3-4B"
    qwen_device: Literal["auto", "cuda", "cpu", "mps"] = "auto"
    qwen_dtype: Literal["auto", "bfloat16", "float16", "float32"] = "auto"
    qwen_max_input_tokens: int = Field(default=24_576, ge=512)
    qwen_max_new_tokens: int = Field(default=5_120, ge=64)
    qwen_max_concurrent_generations: int = Field(default=1, ge=1, le=8)
    qwen_top_p: float = Field(default=0.9, gt=0, le=1)
    qwen_trust_remote_code: bool = False

    tavily_api_key: str = ""
    tavily_search_depth: Literal["basic", "advanced"] = "advanced"
    tavily_timeout_seconds: int = 30
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
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "vlegal_legal_chunks"
    qdrant_vector_name: str = "abstract-dense-vector"
    qdrant_vector_size: int = 1536

    legal_data_dir: str = str(PROJECT_ROOT / "Data (1)")
    legal_storage_dir: str = str(PROJECT_ROOT / "storage" / "graphrag")
    legal_graphrag_db: str = str(PROJECT_ROOT / "storage" / "graphrag" / "legal_graphrag.sqlite")

    aws_region: str = "ap-southeast-1"
    s3_bucket: str = ""

    @field_validator(
        "cors_origins",
        "official_legal_domains",
        "oidc_admin_groups",
        "oidc_reviewer_groups",
        mode="before",
    )
    @classmethod
    def split_csv(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
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
            "neo4j_qdrant": "hybrid_rag",
            "qdrant": "rag",
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
        return bool(self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret and self.oidc_redirect_uri)

    @property
    def qwen_ready(self) -> bool:
        model_path = Path(self.qwen_model_path).expanduser()
        if not model_path.is_absolute():
            model_path = PROJECT_ROOT / model_path
        return model_path.is_dir() and (model_path / "config.json").is_file()

    @property
    def qwen_local_path(self) -> Path:
        model_path = Path(self.qwen_model_path).expanduser()
        return model_path if model_path.is_absolute() else PROJECT_ROOT / model_path

    @property
    def tavily_ready(self) -> bool:
        return bool(self.tavily_api_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
