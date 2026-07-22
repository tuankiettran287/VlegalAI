from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, text as sql_text

from app.core.config import Settings
from app.core.redis_client import create_async_redis
from app.db import SessionFactory
from app.models import LegalDocument
from app.schemas import VerificationItem, VerificationReport
from app.services.ai import QwenService
from app.services.indexer import LegalCandidate, LegalIndexer
from app.services.tavily import TavilyError, TavilyService


LAW_CODE_RE = re.compile(r"\b\d{1,4}/\d{4}/[A-ZĐ][A-ZĐ0-9-]{1,30}\b", re.IGNORECASE)
CURRENT_STATUSES = {"IN_FORCE", "PARTIALLY_IN_FORCE", "AMENDED"}


class FreshnessUnavailable(RuntimeError):
    pass


VERDICT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["code", "title", "status", "source_url", "replacement_code", "replacement_title", "replacement_url", "reason", "confidence"],
    "properties": {
        "code": {"type": "string"},
        "title": {"type": "string"},
        "status": {
            "type": "string",
            "enum": ["IN_FORCE", "PARTIALLY_IN_FORCE", "AMENDED", "EXPIRED", "REPLACED", "UNKNOWN"],
        },
        "source_url": {"type": ["string", "null"]},
        "replacement_code": {"type": ["string", "null"]},
        "replacement_title": {"type": ["string", "null"]},
        "replacement_url": {"type": ["string", "null"]},
        "reason": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
    },
}


def _law_identity(source: dict[str, Any]) -> tuple[str, str, str | None]:
    label = f"{source.get('citation', '')} {source.get('title', '')}"
    match = LAW_CODE_RE.search(label.upper())
    code = match.group(0) if match else str(source.get("doc_id") or source.get("title") or "Không rõ")[:120]
    title = str(source.get("title") or source.get("citation") or code)[:500]
    return code, title, source.get("doc_id")


class LegalFreshnessService:
    def __init__(self, settings: Settings, ai: QwenService, tavily: TavilyService, indexer: LegalIndexer):
        self.settings = settings
        self.ai = ai
        self.tavily = tavily
        self.indexer = indexer
        self.redis = create_async_redis(settings)
        self.semaphore = asyncio.Semaphore(settings.legal_verification_concurrency)

    async def close(self) -> None:
        await self.redis.aclose()

    async def verify_sources(self, sources: list[dict[str, Any]]) -> tuple[VerificationReport, bool]:
        identities: list[tuple[str, str, str | None]] = []
        seen: set[str] = set()
        for source in sources:
            identity = _law_identity(source)
            if identity[0] not in seen:
                seen.add(identity[0])
                identities.append(identity)
            if len(identities) >= self.settings.max_laws_verified_per_request:
                break
        if not identities:
            return VerificationReport(checked=True, all_current=True, checked_at=datetime.now(UTC), note="Không có văn bản cần kiểm tra."), False
        if not self.settings.tavily_ready:
            if self.settings.require_freshness_check:
                raise FreshnessUnavailable("Không thể trả lời trước khi cấu hình TAVILY_API_KEY để kiểm tra hiệu lực văn bản")
            return VerificationReport(checked=False, all_current=False, note="Chưa cấu hình công cụ kiểm tra hiệu lực."), False

        results = await asyncio.gather(*(self._verify_one(*identity) for identity in identities), return_exceptions=True)
        items: list[VerificationItem] = []
        updated = False
        failures: list[str] = []
        for identity, result in zip(identities, results, strict=True):
            if isinstance(result, Exception):
                failures.append(f"{identity[0]}: {result}")
            else:
                item, changed = result
                items.append(item)
                updated = updated or changed
        if failures and self.settings.require_freshness_check:
            raise FreshnessUnavailable("; ".join(failures))
        all_current = bool(items) and all(item.status in CURRENT_STATUSES for item in items)
        return (
            VerificationReport(
                checked=not failures,
                all_current=all_current and not failures,
                checked_at=datetime.now(UTC),
                items=items,
                note=("Đã đối chiếu nguồn chính thức trước khi trả lời." if not failures else "Một số văn bản chưa kiểm tra được: " + "; ".join(failures)),
            ),
            updated,
        )

    async def _verify_one(self, code: str, title: str, external_doc_id: str | None) -> tuple[VerificationItem, bool]:
        async with self.semaphore:
            cutoff = datetime.now(UTC) - timedelta(hours=self.settings.legal_freshness_ttl_hours)
            async with SessionFactory() as db:
                conditions = [LegalDocument.code == code]
                if external_doc_id:
                    conditions.append(LegalDocument.external_doc_id == external_doc_id)
                document = await db.scalar(
                    select(LegalDocument).where(or_(*conditions))
                )
                if document and document.verified_at and document.verified_at >= cutoff:
                    return self._item(document, False), False

            lock_key = f"vlegal:freshness:{code}"
            lock_token = f"{datetime.now(UTC).timestamp()}"
            acquired = False
            try:
                acquired = bool(
                    await self.redis.set(lock_key, lock_token, ex=self.settings.freshness_lock_ttl_seconds, nx=True)
                )
            except Exception:
                acquired = True
            if not acquired:
                for _ in range(20):
                    await asyncio.sleep(0.25)
                    async with SessionFactory() as db:
                        cached = await db.scalar(select(LegalDocument).where(LegalDocument.code == code))
                        if cached and cached.verified_at and cached.verified_at >= cutoff:
                            return self._item(cached, False), False

            try:
                return await self._search_verify_and_update(code, title, external_doc_id)
            finally:
                if acquired:
                    try:
                        current = await self.redis.get(lock_key)
                        if current == lock_token:
                            await self.redis.delete(lock_key)
                    except Exception:
                        pass

    async def _search_verify_and_update(
        self, code: str, title: str, external_doc_id: str | None
    ) -> tuple[VerificationItem, bool]:
        query = f'"{code}" "{title}" hiệu lực hết hiệu lực thay thế sửa đổi văn bản pháp luật Việt Nam'
        results = await self.tavily.search(
            query,
            include_domains=self.settings.official_legal_domains,
            max_results=8,
            include_raw_content=True,
        )
        if not results:
            raise TavilyError(f"Không tìm thấy nguồn chính thức cho {code}")
        raw_content_by_url = {
            row.get("url"): (row.get("raw_content") or row.get("content") or "")
            for row in results
            if row.get("url")
        }
        evidence = [
            {
                "title": row.get("title"),
                "url": row.get("url"),
                "content": (row.get("raw_content") or row.get("content") or "")[:7000],
                "score": row.get("score"),
                "published_date": row.get("published_date"),
            }
            for row in results
        ]
        verdict = await self.ai.complete_json(
            """Bạn là bộ kiểm định hiệu lực văn bản pháp luật Việt Nam. Chỉ dùng bằng chứng từ các tên miền chính thức.
Phân loại IN_FORCE, PARTIALLY_IN_FORCE, AMENDED, EXPIRED, REPLACED hoặc UNKNOWN.
Nếu hết hiệu lực/thay thế phải trả replacement_code, replacement_title và replacement_url khi bằng chứng nêu rõ.
source_url phải là URL chính thức trực tiếp tốt nhất. Không suy đoán khi bằng chứng không đủ.""",
            f"Ngày kiểm tra (UTC): {datetime.now(UTC).date().isoformat()}\n"
            f"Văn bản cần kiểm tra: {code} — {title}\nBằng chứng Tavily:\n{json.dumps(evidence, ensure_ascii=False)}",
            schema=VERDICT_SCHEMA,
            max_tokens=1500,
        )
        checked_at = datetime.now(UTC)
        candidate_url = verdict.get("replacement_url") if verdict["status"] in {"EXPIRED", "REPLACED"} else verdict.get("source_url")
        candidate_code = verdict.get("replacement_code") if verdict["status"] in {"EXPIRED", "REPLACED"} else verdict.get("code") or code
        candidate_title = (
            verdict.get("replacement_title")
            if verdict["status"] in {"EXPIRED", "REPLACED"}
            else verdict.get("title")
        ) or title
        candidate_content = raw_content_by_url.get(candidate_url)
        changed = False

        async with SessionFactory() as db:
            await db.execute(sql_text("SELECT pg_advisory_xact_lock(hashtext(:code))"), {"code": code})
            conditions = [LegalDocument.code == code]
            if external_doc_id:
                conditions.append(LegalDocument.external_doc_id == external_doc_id)
            document = await db.scalar(
                select(LegalDocument).where(or_(*conditions))
            )
            if not document:
                document = LegalDocument(code=code, title=title, external_doc_id=external_doc_id)
                db.add(document)
                await db.flush()
            document.status = verdict["status"]
            document.source_url = verdict.get("source_url") or document.source_url
            document.replaced_by_code = verdict.get("replacement_code")
            document.verified_at = checked_at
            document.verification_payload = {"verdict": verdict, "evidence": evidence}

            if candidate_url and candidate_code and (
                verdict["status"] in {"EXPIRED", "REPLACED", "AMENDED", "PARTIALLY_IN_FORCE"}
                or not document.checksum
            ):
                candidate = LegalCandidate(
                    code=candidate_code,
                    title=candidate_title,
                    url=candidate_url,
                    status="IN_FORCE" if verdict["status"] in {"EXPIRED", "REPLACED"} else verdict["status"],
                    external_doc_id=None if candidate_code != code else external_doc_id,
                    replaces_code=code if candidate_code != code else None,
                    content=candidate_content,
                )
                indexed = await self.indexer.index_candidate(db, candidate)
                indexed.verified_at = checked_at
                indexed.verification_payload = {"discovered_from": code, "verdict": verdict, "evidence": evidence}
                changed = True
            await db.commit()
            await db.refresh(document)
            return self._item(document, changed), changed

    @staticmethod
    def _item(document: LegalDocument, updated: bool) -> VerificationItem:
        return VerificationItem(
            code=document.code,
            title=document.title,
            status=document.status,
            checked_at=document.verified_at or datetime.now(UTC),
            source_url=document.source_url,
            replacement_code=document.replaced_by_code,
            index_updated=updated,
        )
