from __future__ import annotations

import asyncio
import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api import router as api_router
from app.core.config import get_settings
from app.services.ai import QwenError, QwenService
from app.services.articles import ArticleResearchService
from app.services.freshness import LegalFreshnessService
from app.services.guest_limit import GuestRateLimiter
from app.services.indexer import LegalIndexer
from app.services.retrieval import RetrievalService
from app.services.tavily import TavilyError, TavilyService


settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ai = QwenService(settings)
    tavily = TavilyService(settings)
    indexer = LegalIndexer(settings)
    retrieval = RetrievalService(settings)
    freshness = LegalFreshnessService(settings, ai, tavily, indexer)
    guest_limiter = GuestRateLimiter(settings)
    app.state.ai = ai
    app.state.tavily = tavily
    app.state.indexer = indexer
    app.state.retrieval = retrieval
    app.state.freshness = freshness
    app.state.guest_limiter = guest_limiter
    app.state.article_research = ArticleResearchService(tavily, ai)
    app.state.request_slots = asyncio.Semaphore(max(32, settings.database_pool_size * 4))
    yield
    await freshness.close()
    await guest_limiter.close()
    await retrieval.close()
    await ai.close()


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
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    async with request.app.state.request_slots:
        response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.exception_handler(QwenError)
async def qwen_error(_: Request, exc: QwenError) -> JSONResponse:
    logger.error("Qwen offline unavailable: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "Qwen offline hiện chưa sẵn sàng.", "code": "QWEN_UNAVAILABLE"},
    )


@app.exception_handler(TavilyError)
async def tavily_error(_: Request, exc: TavilyError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc), "code": "FRESHNESS_CHECK_UNAVAILABLE"})


app.include_router(api_router, prefix=settings.api_prefix)

@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {"service": "vlegal-api", "status": "ok"}
