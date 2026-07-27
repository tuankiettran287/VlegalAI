from __future__ import annotations

import json
import math
import os
import random
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import google.auth
import httpx
from google.auth.credentials import Credentials
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
DEFAULT_EMBEDDING_DIMENSIONS = 1024
EMBEDDING_PROVIDER_REVISION = "vertex-ai-v1"
GEMINI_API_PROVIDER_REVISION = "gemini-api-v1"
VERTEX_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
VERTEX_API_SERVICE = "aiplatform.googleapis.com"
GEMINI_API_SERVICE = "generativelanguage.googleapis.com"
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}
VERTEX_LOCATION_RE = re.compile(r"^[a-z][a-z0-9-]{0,61}[a-z0-9]$")
EMBEDDING_PROVIDERS = {"vertex", "gemini-api"}


class EmbeddingModelError(RuntimeError):
    """Raised when embedding credentials, requests, or responses are invalid."""


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class EmbeddingConfig:
    provider: str = "vertex"
    model: str = DEFAULT_EMBEDDING_MODEL
    project_id: str = ""
    location: str = "asia-southeast1"
    credentials_path: str = str(PROJECT_ROOT / "env.json")
    use_adc: bool = False
    api_key: str = field(default="", repr=False)
    dimensions: int = DEFAULT_EMBEDDING_DIMENSIONS
    max_concurrency: int = 8
    batch_size: int = 20
    max_items_per_minute: int = 0
    timeout_seconds: float = 60.0
    max_retries: int = 3
    auto_truncate: bool = True
    data_policy: str = "redact"

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        return cls(
            provider=os.getenv("EMBEDDING_PROVIDER", "vertex"),
            model=os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
            project_id=os.getenv("GEMINI_PROJECT_ID", ""),
            location=os.getenv(
                "EMBEDDING_LOCATION",
                "asia-southeast1",
            ),
            credentials_path=os.getenv(
                "GEMINI_CREDENTIALS_PATH",
                str(PROJECT_ROOT / "env.json"),
            ),
            use_adc=_env_bool("GEMINI_USE_ADC"),
            api_key=os.getenv("GEMINI_API_KEY", ""),
            dimensions=int(
                os.getenv("POSTGRES_VECTOR_SIZE", str(DEFAULT_EMBEDDING_DIMENSIONS))
            ),
            max_concurrency=int(os.getenv("EMBEDDING_MAX_CONCURRENCY", "8")),
            batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "20")),
            max_items_per_minute=int(
                os.getenv("EMBEDDING_MAX_ITEMS_PER_MINUTE", "0")
            ),
            timeout_seconds=float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60")),
            max_retries=int(os.getenv("EMBEDDING_MAX_RETRIES", "3")),
            auto_truncate=_env_bool("EMBEDDING_AUTO_TRUNCATE", True),
            data_policy=os.getenv("GEMINI_DATA_POLICY", "redact")
            .strip()
            .lower(),
        )

    @property
    def credentials_local_path(self) -> Path:
        path = Path(self.credentials_path).expanduser()
        return path if path.is_absolute() else PROJECT_ROOT / path

    @property
    def model_revision(self) -> str:
        revision = (
            GEMINI_API_PROVIDER_REVISION
            if self.normalized_provider == "gemini-api"
            else EMBEDDING_PROVIDER_REVISION
        )
        return f"{revision}:{self.data_policy}"

    @property
    def normalized_provider(self) -> str:
        return self.provider.strip().lower().replace("_", "-")

    @property
    def identity(self) -> str:
        return f"{self.model}@{self.model_revision}"

    @property
    def ready(self) -> bool:
        provider = self.normalized_provider
        credentials_configured = (
            bool(self.api_key.strip())
            if provider == "gemini-api"
            else bool(
                os.getenv("GEMINI_CREDENTIALS_JSON", "").strip()
                or self.credentials_local_path.is_file()
                or self.use_adc
            )
        )
        return bool(
            provider in EMBEDDING_PROVIDERS
            and self.model.strip()
            and (
                provider == "gemini-api"
                or VERTEX_LOCATION_RE.fullmatch(self.location.strip())
            )
            and 128 <= self.dimensions <= 3072
            and self.max_concurrency >= 1
            and 1 <= self.batch_size <= 100
            and self.max_items_per_minute >= 0
            and (
                self.max_items_per_minute == 0
                or self.batch_size <= self.max_items_per_minute
            )
            and self.timeout_seconds > 0
            and self.max_retries >= 1
            and self.data_policy in {"allow", "redact", "deny"}
            and credentials_configured
        )


def embedding_config_from_settings(settings: Any) -> EmbeddingConfig:
    """Build one embedding configuration from application settings."""

    return EmbeddingConfig(
        provider=settings.embedding_provider,
        model=settings.embedding_model,
        project_id=settings.gemini_project_id,
        location=settings.embedding_location,
        credentials_path=settings.gemini_credentials_path,
        use_adc=settings.gemini_use_adc,
        api_key=settings.gemini_api_key,
        dimensions=settings.postgres_vector_size,
        max_concurrency=settings.embedding_max_concurrency,
        batch_size=settings.embedding_batch_size,
        max_items_per_minute=settings.embedding_max_items_per_minute,
        timeout_seconds=settings.embedding_timeout_seconds,
        max_retries=settings.embedding_max_retries,
        auto_truncate=settings.embedding_auto_truncate,
        data_policy=settings.gemini_data_policy,
    )


class VertexAIEmbeddingService:
    """Thread-safe Gemini embedding client for Vertex AI or Gemini API."""

    def __init__(
        self,
        config: EmbeddingConfig,
        *,
        client: httpx.Client | None = None,
    ):
        self.config = config
        self._credentials: Credentials | None = None
        self._project_id = ""
        self._credentials_lock = threading.Lock()
        self._readiness_lock = threading.Lock()
        self._vertex_ready = False
        self._rate_lock = threading.Lock()
        self._rate_events: deque[tuple[float, int]] = deque()
        self._rate_total = 0
        self._owns_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(config.timeout_seconds, connect=15.0),
            limits=httpx.Limits(
                max_connections=config.max_concurrency,
                max_keepalive_connections=config.max_concurrency,
            ),
        )

    @property
    def _provider(self) -> str:
        provider = self.config.normalized_provider
        if provider not in EMBEDDING_PROVIDERS:
            raise EmbeddingModelError(
                "EMBEDDING_PROVIDER must be 'vertex' or 'gemini-api'."
            )
        return provider

    def _load_credentials(self) -> tuple[Credentials, str]:
        detected_project_id = ""
        json_env = os.getenv("GEMINI_CREDENTIALS_JSON", "").strip()
        if json_env:
            try:
                info = json.loads(json_env)
                credentials = service_account.Credentials.from_service_account_info(
                    info,
                    scopes=[VERTEX_SCOPE],
                )
                detected_project_id = str(credentials.project_id or "").strip()
            except Exception as exc:
                raise EmbeddingModelError(
                    f"Cannot read GEMINI_CREDENTIALS_JSON: {exc}"
                ) from exc
        elif self.config.credentials_local_path.is_file():
            try:
                credentials = service_account.Credentials.from_service_account_file(
                    self.config.credentials_local_path,
                    scopes=[VERTEX_SCOPE],
                )
                detected_project_id = str(credentials.project_id or "").strip()
            except (OSError, ValueError) as exc:
                raise EmbeddingModelError(
                    "Cannot read the configured Vertex AI service-account credential."
                ) from exc
        elif self.config.use_adc:
            try:
                credentials, detected_project_id = google.auth.default(
                    scopes=[VERTEX_SCOPE]
                )
            except DefaultCredentialsError as exc:
                raise EmbeddingModelError(
                    "Application Default Credentials are unavailable for Vertex AI embeddings."
                ) from exc
        else:
            raise EmbeddingModelError(
                "Vertex AI embedding credentials are not configured."
            )

        project_id = self.config.project_id.strip() or str(
            detected_project_id or ""
        ).strip()
        if not project_id:
            raise EmbeddingModelError(
                "Vertex AI embedding project ID is not configured."
            )
        return credentials, project_id

    def _ensure_credentials(self) -> Credentials:
        if self._credentials is not None:
            return self._credentials
        with self._credentials_lock:
            if self._credentials is None:
                self._credentials, self._project_id = self._load_credentials()
        return self._credentials

    def _access_token(self, *, force_refresh: bool = False) -> str:
        credentials = self._ensure_credentials()
        with self._credentials_lock:
            if force_refresh or not credentials.valid:
                try:
                    credentials.refresh(GoogleAuthRequest())
                except Exception as exc:
                    raise EmbeddingModelError(
                        "Cannot authenticate the Vertex AI embedding request."
                    ) from exc
            if not credentials.token:
                raise EmbeddingModelError(
                    "Google Cloud did not return an access token for Vertex AI embeddings."
                )
            return credentials.token

    @property
    def _predict_url(self) -> str:
        if self._provider != "vertex":
            raise EmbeddingModelError(
                "The Vertex AI prediction endpoint requires EMBEDDING_PROVIDER=vertex."
            )
        location = self.config.location.strip()
        model = self.config.model.strip()
        if not VERTEX_LOCATION_RE.fullmatch(location) or not model:
            raise EmbeddingModelError(
                "Vertex AI embedding model and a valid location must be configured."
            )
        self._ensure_credentials()
        api_host = (
            VERTEX_API_SERVICE
            if location == "global"
            else f"{location}-{VERTEX_API_SERVICE}"
        )
        return (
            f"https://{api_host}/v1/"
            f"projects/{quote(self._project_id, safe='')}/"
            f"locations/{quote(location, safe='')}/publishers/google/models/"
            f"{quote(model, safe='')}:predict"
        )

    def _gemini_api_url(self, action: str) -> str:
        if self._provider != "gemini-api":
            raise EmbeddingModelError(
                "The Gemini API endpoint requires EMBEDDING_PROVIDER=gemini-api."
            )
        model = self.config.model.strip()
        api_key = self.config.api_key.strip()
        if not model:
            raise EmbeddingModelError(
                "Gemini API embedding model is not configured."
            )
        if not api_key:
            raise EmbeddingModelError(
                "GEMINI_API_KEY is required for Gemini API embeddings."
            )
        return (
            f"https://{GEMINI_API_SERVICE}/v1beta/models/"
            f"{quote(model, safe='')}:{action}"
        )

    @staticmethod
    def _response_detail(response: httpx.Response) -> str:
        try:
            payload = response.json()
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            detail = error.get("message") if isinstance(error, dict) else None
        except (TypeError, ValueError):
            detail = None
        return str(detail or response.text or "no details")[:500]

    def _normalize_vector(self, values: Any, *, provider_label: str) -> list[float]:
        try:
            vector = [float(value) for value in values]
        except (TypeError, ValueError) as exc:
            raise EmbeddingModelError(
                f"{provider_label} embedding response has an invalid vector."
            ) from exc
        if len(vector) != self.config.dimensions:
            raise EmbeddingModelError(
                f"{provider_label} embedding returned {len(vector)} dimensions; "
                f"expected {self.config.dimensions}."
            )
        if not all(math.isfinite(value) for value in vector):
            raise EmbeddingModelError(
                f"{provider_label} embedding response contains non-finite values."
            )

        # gemini-embedding-001 does not normalize reduced-dimensional output.
        magnitude = math.sqrt(sum(value * value for value in vector))
        if not math.isfinite(magnitude) or magnitude <= 0:
            raise EmbeddingModelError(
                f"{provider_label} embedding response has zero magnitude."
            )
        return [value / magnitude for value in vector]

    def _parse_vertex_vector(self, response: httpx.Response) -> list[float]:
        try:
            payload = response.json()
            values = payload["predictions"][0]["embeddings"]["values"]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise EmbeddingModelError(
                "Vertex AI embedding response has an invalid structure."
            ) from exc
        return self._normalize_vector(values, provider_label="Vertex AI")

    def _parse_gemini_vectors(
        self,
        response: httpx.Response,
        *,
        expected_count: int,
    ) -> list[list[float]]:
        try:
            payload = response.json()
            if expected_count == 1 and "embedding" in payload:
                embeddings = [payload["embedding"]]
            else:
                embeddings = payload["embeddings"]
            if len(embeddings) != expected_count:
                raise ValueError("embedding count mismatch")
            values_list = [embedding["values"] for embedding in embeddings]
        except (KeyError, TypeError, ValueError) as exc:
            raise EmbeddingModelError(
                "Gemini API embedding response has an invalid structure."
            ) from exc
        return [
            self._normalize_vector(values, provider_label="Gemini API")
            for values in values_list
        ]

    def _prepare_text(self, text: str) -> str:
        policy = self.config.data_policy
        if policy == "allow":
            return text
        if policy not in {"redact", "deny"}:
            raise EmbeddingModelError(
                "Embedding data policy is invalid."
            )

        # Import lazily so the standalone reindex path does not create a
        # module-level dependency cycle between the AI and embedding clients.
        from app.services.ai import redact_sensitive_text

        redacted, count = redact_sensitive_text(text)
        if count and policy == "deny":
            raise EmbeddingModelError(
                "Sensitive data cannot be sent to embeddings under "
                "the current data policy."
            )
        return redacted

    @staticmethod
    def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
        if response is not None:
            retry_after = response.headers.get("retry-after", "").strip()
            try:
                if retry_after:
                    return min(max(float(retry_after), 0.0), 60.0)
            except ValueError:
                pass
        return min(2**attempt, 60) + random.uniform(0, 0.25)

    def _request_vertex_one(self, text: str, task_type: str) -> list[float]:
        last_error: EmbeddingModelError | None = None
        force_refresh = False
        payload = {
            "instances": [
                {
                    "content": self._prepare_text(text),
                    "task_type": task_type,
                }
            ],
            "parameters": {
                "autoTruncate": self.config.auto_truncate,
                "outputDimensionality": self.config.dimensions,
            },
        }
        for attempt in range(self.config.max_retries):
            response: httpx.Response | None = None
            token = self._access_token(force_refresh=force_refresh)
            force_refresh = False
            try:
                response = self._client.post(
                    self._predict_url,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    json=payload,
                )
            except httpx.HTTPError as exc:
                last_error = EmbeddingModelError(
                    "Cannot connect to the Vertex AI embedding endpoint."
                )
                if attempt + 1 >= self.config.max_retries:
                    raise last_error from exc
            else:
                if response.status_code == 200:
                    return self._parse_vertex_vector(response)
                last_error = EmbeddingModelError(
                    f"Vertex AI embedding returned HTTP {response.status_code}: "
                    f"{self._response_detail(response)}"
                )
                if (
                    response.status_code == 401
                    and attempt + 1 < self.config.max_retries
                ):
                    force_refresh = True
                elif (
                    response.status_code not in RETRYABLE_STATUS_CODES
                    or attempt + 1 >= self.config.max_retries
                ):
                    raise last_error

            time.sleep(self._retry_delay(response, attempt))
        raise last_error or EmbeddingModelError(
            "Vertex AI embedding request failed."
        )

    def _gemini_embed_request(self, text: str, task_type: str) -> dict[str, Any]:
        model = f"models/{self.config.model.strip()}"
        return {
            "model": model,
            "content": {
                "parts": [{"text": self._prepare_text(text)}],
            },
            "taskType": task_type,
            "outputDimensionality": self.config.dimensions,
        }

    def _throttle_gemini_items(self, item_count: int) -> None:
        limit = self.config.max_items_per_minute
        if limit <= 0:
            return
        if item_count > limit:
            raise EmbeddingModelError(
                "EMBEDDING_BATCH_SIZE cannot exceed "
                "EMBEDDING_MAX_ITEMS_PER_MINUTE."
            )

        while True:
            wait_seconds = 0.0
            with self._rate_lock:
                now = time.monotonic()
                cutoff = now - 60.0
                while (
                    self._rate_events
                    and self._rate_events[0][0] <= cutoff
                ):
                    _, expired_count = self._rate_events.popleft()
                    self._rate_total -= expired_count

                if self._rate_total + item_count <= limit:
                    self._rate_events.append((now, item_count))
                    self._rate_total += item_count
                    return

                wait_seconds = max(
                    self._rate_events[0][0] + 60.0 - now,
                    0.01,
                )
            time.sleep(wait_seconds)

    def _request_gemini_batch(
        self,
        texts: list[str],
        task_type: str,
    ) -> list[list[float]]:
        if not texts:
            return []
        requests = [
            self._gemini_embed_request(text, task_type)
            for text in texts
        ]
        is_single = len(requests) == 1
        action = "embedContent" if is_single else "batchEmbedContents"
        payload = requests[0] if is_single else {"requests": requests}
        last_error: EmbeddingModelError | None = None

        for attempt in range(self.config.max_retries):
            response: httpx.Response | None = None
            self._throttle_gemini_items(len(requests))
            try:
                response = self._client.post(
                    self._gemini_api_url(action),
                    headers={
                        "x-goog-api-key": self.config.api_key.strip(),
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    json=payload,
                )
            except httpx.HTTPError as exc:
                last_error = EmbeddingModelError(
                    "Cannot connect to the Gemini API embedding endpoint."
                )
                if attempt + 1 >= self.config.max_retries:
                    raise last_error from exc
            else:
                if response.status_code == 200:
                    return self._parse_gemini_vectors(
                        response,
                        expected_count=len(requests),
                    )
                last_error = EmbeddingModelError(
                    f"Gemini API embedding returned HTTP {response.status_code}: "
                    f"{self._response_detail(response)}"
                )
                if (
                    response.status_code not in RETRYABLE_STATUS_CODES
                    or attempt + 1 >= self.config.max_retries
                ):
                    raise last_error

            time.sleep(self._retry_delay(response, attempt))
        raise last_error or EmbeddingModelError(
            "Gemini API embedding request failed."
        )

    def _request_one(self, text: str, task_type: str) -> list[float]:
        if self._provider == "gemini-api":
            return self._request_gemini_batch([text], task_type)[0]
        return self._request_vertex_one(text, task_type)

    def _encode(
        self,
        texts: list[str],
        *,
        task_type: str,
        show_progress: bool = False,
    ) -> list[list[float]]:
        del show_progress
        if not texts:
            return []
        if self._provider == "gemini-api":
            batches = [
                texts[offset : offset + self.config.batch_size]
                for offset in range(0, len(texts), self.config.batch_size)
            ]
            if len(batches) == 1 or self.config.max_concurrency == 1:
                return [
                    vector
                    for batch in batches
                    for vector in self._request_gemini_batch(batch, task_type)
                ]
            with ThreadPoolExecutor(
                max_workers=min(self.config.max_concurrency, len(batches))
            ) as executor:
                batch_vectors = list(
                    executor.map(
                        lambda batch: self._request_gemini_batch(
                            batch,
                            task_type,
                        ),
                        batches,
                    )
                )
            return [
                vector
                for vectors in batch_vectors
                for vector in vectors
            ]
        if len(texts) == 1 or self.config.max_concurrency == 1:
            return [self._request_one(text, task_type) for text in texts]
        with ThreadPoolExecutor(
            max_workers=min(self.config.max_concurrency, len(texts))
        ) as executor:
            return list(
                executor.map(
                    lambda text: self._request_one(text, task_type),
                    texts,
                )
            )

    def embed_documents(
        self,
        texts: Iterable[str],
        *,
        show_progress: bool = False,
    ) -> list[list[float]]:
        return self._encode(
            [str(text or "") for text in texts],
            task_type="RETRIEVAL_DOCUMENT",
            show_progress=show_progress,
        )

    def embed_query(self, text: str) -> list[float]:
        return self._request_one(str(text or ""), "RETRIEVAL_QUERY")

    def embed_similarity(self, text: str) -> list[float]:
        """Embed text for symmetric text-to-text similarity comparisons."""

        return self._request_one(str(text or ""), "SEMANTIC_SIMILARITY")

    def ensure_ready(self) -> None:
        if self._vertex_ready:
            return
        with self._readiness_lock:
            if not self._vertex_ready:
                self._request_one("readiness", "RETRIEVAL_QUERY")
                self._vertex_ready = True

    def close(self) -> None:
        if self._owns_client:
            self._client.close()


@lru_cache(maxsize=8)
def get_embedding_service(
    config: EmbeddingConfig | None = None,
) -> VertexAIEmbeddingService:
    return VertexAIEmbeddingService(config or EmbeddingConfig.from_env())
