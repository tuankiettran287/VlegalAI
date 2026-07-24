from __future__ import annotations

import asyncio
import logging
import re
import uuid
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api import router as api_router
from app.core.config import get_settings
from app.services.ai import GeminiError, GeminiService
from app.services.articles import ArticleResearchError, ArticleResearchService
from app.services.conversation_memory import ConversationMemoryService
from app.services.freshness import LegalFreshnessService
from app.services.google_search import GoogleSearchService
from app.services.guest_limit import GuestRateLimiter
from app.services.indexer import LegalIndexer
from app.services.retrieval import RetrievalService
from app.services.semantic_cache import SemanticAnswerCacheService
from app.services.tavily import TavilyError, TavilyService


settings = get_settings()
logger = logging.getLogger(__name__)
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def _normalized_request_id(value: str | None) -> str:
    candidate = (value or "").strip()
    if REQUEST_ID_RE.fullmatch(candidate):
        return candidate
    return uuid.uuid4().hex


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with AsyncExitStack() as stack:
        ai = GeminiService(settings)
        stack.push_async_callback(ai.close)
        tavily = TavilyService(settings)
        google_search = GoogleSearchService(settings, ai)
        indexer = LegalIndexer(settings)
        retrieval = RetrievalService(settings)
        stack.push_async_callback(retrieval.close)
        freshness = LegalFreshnessService(settings, ai, tavily, google_search, indexer)
        guest_limiter = GuestRateLimiter(settings)
        app.state.ai = ai
        app.state.tavily = tavily
        app.state.google_search = google_search
        app.state.indexer = indexer
        app.state.retrieval = retrieval
        app.state.freshness = freshness
        app.state.guest_limiter = guest_limiter
        app.state.conversation_memory = ConversationMemoryService(settings, ai)
        app.state.semantic_answer_cache = SemanticAnswerCacheService(settings)
        app.state.article_research = ArticleResearchService(tavily, google_search, ai)
        app.state.request_slots = asyncio.Semaphore(max(32, settings.database_pool_size * 4))
        yield


app = FastAPI(
    title="VLegal AI API",
    description="Vietnamese legal research, contract AI and current-law GraphRAG platform",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url=None,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
)


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = _normalized_request_id(request.headers.get("X-Request-ID"))
    request.state.request_id = request_id
    async with request.app.state.request_slots:
        response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


def _safe_request_id(request: Request | None) -> str:
    return str(getattr(getattr(request, "state", None), "request_id", "") or "")


@app.exception_handler(GeminiError)
async def gemini_error(request: Request, exc: GeminiError) -> JSONResponse:
    request_id = _safe_request_id(request)
    logger.error(
        "Gemini generation unavailable request_id=%s error_type=%s",
        request_id,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Dịch vụ AI tạm thời không thể tạo phản hồi an toàn.",
            "code": "GEMINI_UNAVAILABLE",
            "request_id": request_id,
        },
    )


@app.exception_handler(TavilyError)
async def tavily_error(request: Request, exc: TavilyError) -> JSONResponse:
    request_id = _safe_request_id(request)
    logger.error(
        "Tavily unavailable request_id=%s error_type=%s",
        request_id,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Dịch vụ kiểm tra hiệu lực tạm thời không khả dụng.",
            "code": "FRESHNESS_CHECK_UNAVAILABLE",
            "request_id": request_id,
        },
    )


@app.exception_handler(ArticleResearchError)
async def article_research_error(request: Request, exc: ArticleResearchError) -> JSONResponse:
    request_id = _safe_request_id(request)
    logger.error(
        "Article research unavailable request_id=%s error_type=%s",
        request_id,
        type(exc).__name__,
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Dịch vụ tìm kiếm bài viết tạm thời không khả dụng.",
            "code": "WEB_SEARCH_UNAVAILABLE",
            "request_id": request_id,
        },
    )


from app.auth import router as auth_router
app.include_router(api_router, prefix=settings.api_prefix)
app.include_router(auth_router, prefix="/api")

@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "vlegal-api", "status": "ok"}
