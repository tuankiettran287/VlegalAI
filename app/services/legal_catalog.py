from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


CATALOG_TYPES = {
    "DECREE": "nghị định",
    "CIRCULAR": "thông tư",
    "CODE": "bộ luật",
    "LAW": "luật",
    "CONSOLIDATED": "văn bản hợp nhất",
    "RESOLUTION": "nghị quyết",
    "DECISION": "quyết định",
    "OTHER": "văn bản khác",
}

STATUS_LABELS = {
    "CURRENT": "đang còn hiệu lực",
    "IN_FORCE": "đang có hiệu lực",
    "PARTIALLY_IN_FORCE": "còn hiệu lực một phần",
    "AMENDED": "đã được sửa đổi nhưng còn áp dụng",
    "EXPIRED": "hết hiệu lực",
    "REPLACED": "đã được thay thế",
    "NOT_YET_EFFECTIVE": "chưa có hiệu lực",
    "UNKNOWN": "chưa xác định",
    "UNVERIFIED": "chưa được kiểm chứng",
}

_TYPE_PATTERNS = (
    ("DECREE", re.compile(r"\bnghi\s+dinh\b")),
    ("CIRCULAR", re.compile(r"\bthong\s+tu\b")),
    ("CODE", re.compile(r"\bbo\s+luat\b")),
    ("CONSOLIDATED", re.compile(r"\bvan\s+ban\s+hop\s+nhat\b")),
    ("RESOLUTION", re.compile(r"\bnghi\s+quyet\b")),
    ("DECISION", re.compile(r"\bquyet\s+dinh\b")),
    ("LAW", re.compile(r"\bluat\b")),
)
_COUNT_RE = re.compile(r"\b(?:co\s+)?bao\s+nhieu\b|\btong\s+so\b")
_LIST_RE = re.compile(
    r"\bliet\s+ke\b|\bdanh\s+sach\b|\bdanh\s+muc\b|\bgom\s+nhung\b|\bdang\s+co\b|\bco\s+nhung\b",
    re.IGNORECASE,
)
_SUMMARY_RE = re.compile(
    r"\bthong\s+ke\b|\bphan\s+bo\b|\bthong\s+tin\s+tong\s+quan\b"
)
_CATALOG_SCOPE_RE = re.compile(
    r"\b(?:kho|corpus|co\s+so\s+du\s+lieu|he\s+thong)\s+"
    r"(?:(?:van\s+ban|luat|du\s+lieu)\s+)?(?:vlegal|phap\s+ly|he\s+thong)?\b"
    r"|\b(?:trong|cua)\s+(?:kho\s+|he\s+thong\s+)?vlegal\b"
    r"|\bdu\s+lieu\s+(?:cua\s+)?vlegal\b"
    r"|\bvlegal\s+(?:dang\s+)?co\s+"
    r"|\bhe\s+thong\s+(?:co\s+)?bao\s+nhieu\s+(?:van\s+ban|luat|tai\s+lieu)\b"
    r"|\bdanh\s+muc\s+van\s+ban\b"
    r"|\bliet\s+ke\s+(?:cac\s+)?loai\s+van\s+ban\b",
    re.IGNORECASE,
)
_IN_FORCE_RE = re.compile(r"\b(?:dang|con)\s+(?:co\s+)?hieu\s+luc\b")
_EXPIRED_RE = re.compile(r"\bhet\s+hieu\s+luc\b")


class LegalCatalogUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class CatalogRequest:
    action: str
    document_type: str | None = None
    status: str | None = None
    law_code: str | None = None          # mã số chuẩn hoá (vd: 45/2019/QH14)
    law_name_hint: str | None = None     # tên tự nhiên khi không có mã số


def _ascii_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    return " ".join(
        "".join(char for char in normalized if not unicodedata.combining(char))
        .lower()
        .replace("đ", "d")
        .split()
    )


UNSUPPORTED_OFFICIAL_PATTERNS = [
    re.compile(r"\bco\s+so\s+du\s+lieu\s+phap\s+luat\s+chinh\s+thuc\b"),
    re.compile(r"\btoan\s+bo\s+he\s+thong\s+phap\s+luat\b"),
    re.compile(r"\btat\s+ca\s+van\s+ban\s+hien\s+hanh\b"),
    re.compile(r"\btren\s+toan\s+quoc\b"),
]

SCOPE_REQUIRED_PATTERNS = [
    re.compile(r"\bco\s+bao\s+nhieu\s+dieu\s+luat\b"),
    re.compile(r"\bmay\s+dieu\s+luat\b"),
]

# Phải có từ chỉ loại văn bản pháp luật HOẶC mã số trước cụm “có bao nhiêu/mấy điều”
# → tránh false positive câu như “Cháu có mấy điều muốn hỏi”
ARTICLE_COUNT_PATTERN = re.compile(
    r"\b(?:bo\s+luat|luat|nghi\s+dinh|thong\s+tu|van\s+ban)\s+[a-z0-9][a-z0-9\s\-_\u2013/]*\s*(?:co|gom)\s*(?:bao\s+nhieu|may)\s*dieu\b"
    r"|\b\d{1,3}/\d{4}/[A-Z\u0110][A-Z0-9\u0110\-]*[^/]*(?:co|gom)\s*(?:bao\s+nhieu|may)\s*dieu\b"
    r"|\b(?:co|gom)\s*(?:bao\s+nhieu|may)\s*dieu\b.*\b(?:bo\s+luat|luat|nghi\s+dinh|thong\s+tu)\b",
    re.IGNORECASE,
)

# Regex trích xuất mã số văn bản hình thức từ câu hỏi tự nhiên
# Khớp: 45/2019/QH14, 145/2020/NĐ-CP, 05/2015/NĐ-CP, 43/2013/QH13…
_LAW_CODE_RE = re.compile(
    r"\b(\d{1,3}/\d{4}/[A-Z\u0110][A-Z0-9\u0110\-]*)\b",
    re.IGNORECASE,
)

# Regex trích xuất tên văn bản tự nhiên (dùng làm law_name_hint khi không có mã số)
_LAW_NAME_HINT_RE = re.compile(
    r"\b((?:bo\s+luat|luat|nghi\s+dinh|thong\s+tu)(?:\s+[a-z0-9]+){1,6})\b",
    re.IGNORECASE,
)


def _extract_law_info(normalized_query: str, original_query: str) -> tuple[str | None, str | None]:
    """Return (law_code, law_name_hint) extracted from the query.

    Tries to find a formal law code first (e.g. 45/2019/QH14). If not found,
    falls back to extracting a natural name hint (e.g. 'bo luat lao dong 2019').
    Both can be None if nothing useful is detected.
    """
    # Ưu tiên mã số hình thức từ câu hỏi gốc (trước khi ASCII-normalize)
    code_match = _LAW_CODE_RE.search(original_query)
    if code_match:
        return code_match.group(1), None

    # Thử trích tên tự nhiên từ câu đã normalize
    name_match = _LAW_NAME_HINT_RE.search(normalized_query)
    if name_match:
        raw_name = name_match.group(1).strip()
        cleaned_name = re.sub(
            r"\s+(?:co|gom)\s+(?:bao\s+nhieu|may)\s*(?:dieu)?.*$",
            "",
            raw_name,
            flags=re.IGNORECASE,
        ).strip()
        cleaned_name = re.sub(
            r"\s+(?:co|gom|may|bao|nhieu|dieu)+$",
            "",
            cleaned_name,
            flags=re.IGNORECASE,
        ).strip()
        return None, cleaned_name or raw_name

    return None, None


def parse_catalog_request(query: str) -> CatalogRequest | None:
    """Recognize corpus-scoped catalogue questions and unsupported official queries."""

    normalized = _ascii_text(query)

    for pat in UNSUPPORTED_OFFICIAL_PATTERNS:
        if pat.search(normalized):
            return CatalogRequest(action="unsupported_official_catalog")

    for pat in SCOPE_REQUIRED_PATTERNS:
        if pat.search(normalized):
            return CatalogRequest(action="scope_required")

    if (
        ARTICLE_COUNT_PATTERN.search(normalized)
        and not re.search(
            r"\bco\s+bao\s+nhieu\s+(?:luat|nghi\s+dinh|thong\s+tu)\b",
            normalized,
        )
        and not re.search(r"\bluat\s+su\b", normalized)
    ):
        law_code, law_name_hint = _extract_law_info(normalized, query)
        return CatalogRequest(
            action="article_count",
            law_code=law_code,
            law_name_hint=law_name_hint,
        )

    if not _CATALOG_SCOPE_RE.search(normalized):
        return None
    if not (
        _COUNT_RE.search(normalized)
        or _LIST_RE.search(normalized)
        or _SUMMARY_RE.search(normalized)
    ):
        return None

    document_type = next(
        (
            document_type
            for document_type, pattern in _TYPE_PATTERNS
            if pattern.search(normalized)
        ),
        None,
    )
    status = None
    if _IN_FORCE_RE.search(normalized):
        status = "CURRENT"
    elif _EXPIRED_RE.search(normalized):
        status = "EXPIRED"
    if _LIST_RE.search(normalized):
        action = "list"
    elif _SUMMARY_RE.search(normalized):
        action = "summary"
    else:
        action = "count"
    return CatalogRequest(
        action=action,
        document_type=document_type,
        status=status,
    )


_CATALOG_CTE = """
WITH catalogue AS (
    SELECT
        corpus.law_code_normalized,
        corpus.code,
        coalesce(nullif(document.title, ''), corpus.title) AS title,
        corpus.document_type,
        coalesce(document.issuer, '') AS issuer,
        coalesce(document.source_url, corpus.source_url) AS source_url,
        corpus.corpus_status,
        CASE
            WHEN document.verified_at IS NOT NULL
             AND upper(coalesce(document.status, '')) NOT IN (
                '', 'UNKNOWN', 'UNVERIFIED'
             )
                THEN upper(document.status)
            ELSE corpus.corpus_status
        END AS resolved_status,
        CASE
            WHEN document.verified_at IS NOT NULL
             AND upper(coalesce(document.status, '')) NOT IN (
                '', 'UNKNOWN', 'UNVERIFIED'
             )
                THEN 'VERIFIED_DOCUMENT'
            ELSE 'INDEXED_CORPUS'
        END AS status_source,
        (
            document.verified_at IS NOT NULL
            AND upper(coalesce(document.status, '')) NOT IN (
                '', 'UNKNOWN', 'UNVERIFIED'
            )
            AND corpus.corpus_status NOT IN ('UNKNOWN', 'UNVERIFIED')
            AND upper(document.status) <> corpus.corpus_status
        ) AS status_conflict,
        (document.verified_at IS NOT NULL) AS metadata_verified,
        document.effective_from,
        document.effective_to,
        document.replaced_by_code,
        document.verified_at,
        corpus.law_version,
        corpus.chunk_count,
        corpus.indexed_at,
        corpus.refreshed_at
    FROM legal_catalog_corpus AS corpus
    LEFT JOIN legal_document AS document
      ON upper(
        regexp_replace(
            btrim(document.code),
            '[[:space:]]+',
            '',
            'g'
        )
      ) = corpus.law_code_normalized
)
"""


class LegalCatalogService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def stats(self) -> dict[str, Any]:
        statement = text(
            _CATALOG_CTE
            + """
            SELECT
                count(*)::bigint AS total,
                count(*) FILTER (
                    WHERE metadata_verified
                )::bigint AS metadata_verified,
                count(*) FILTER (
                    WHERE NOT metadata_verified
                )::bigint AS metadata_unverified,
                count(*) FILTER (
                    WHERE source_url IS NULL OR btrim(source_url) = ''
                )::bigint AS missing_source_url,
                count(*) FILTER (
                    WHERE status_conflict
                )::bigint AS status_conflicts,
                max(refreshed_at) AS as_of
            FROM catalogue
            """
        )
        row = (await self._execute(statement)).mappings().one()
        by_type = await self._group_counts("document_type")
        by_status = await self._group_counts("resolved_status")
        return {
            "total": int(row["total"]),
            "by_type": by_type,
            "by_status": by_status,
            "metadata_quality": {
                "verified": int(row["metadata_verified"]),
                "unverified": int(row["metadata_unverified"]),
                "missing_source_url": int(row["missing_source_url"]),
                "status_conflicts": int(row["status_conflicts"]),
            },
            "as_of": row["as_of"],
        }

    async def _group_counts(self, field: str) -> dict[str, int]:
        if field not in {"document_type", "resolved_status"}:
            raise ValueError("Unsupported catalogue grouping")
        result = await self._execute(
            text(
                _CATALOG_CTE
                + f"""
                SELECT {field} AS key, count(*)::bigint AS count
                FROM catalogue
                GROUP BY {field}
                ORDER BY {field}
                """
            )
        )
        return {
            str(row["key"]): int(row["count"])
            for row in result.mappings().all()
        }

    async def documents(
        self,
        *,
        document_type: str | None = None,
        status: str | None = None,
        q: str = "",
        page: int = 1,
        page_size: int = 50,
    ) -> dict[str, Any]:
        conditions = []
        parameters: dict[str, Any] = {
            "offset": (page - 1) * page_size,
            "limit": page_size,
        }
        if document_type:
            conditions.append("document_type = :document_type")
            parameters["document_type"] = document_type.upper()
        if status:
            normalized_status = status.upper()
            if normalized_status == "CURRENT":
                conditions.append(
                    "resolved_status IN "
                    "('CURRENT', 'IN_FORCE', 'PARTIALLY_IN_FORCE', 'AMENDED')"
                )
            else:
                conditions.append("resolved_status = :status")
                parameters["status"] = normalized_status
        if q.strip():
            conditions.append(
                "(code ILIKE :query OR title ILIKE :query)"
            )
            parameters["query"] = f"%{q.strip()}%"
        where_clause = (
            " WHERE " + " AND ".join(conditions) if conditions else ""
        )
        result = await self._execute(
            text(
                _CATALOG_CTE
                + f"""
                SELECT *, (count(*) OVER())::bigint AS catalog_total
                FROM catalogue
                {where_clause}
                ORDER BY document_type, code
                OFFSET :offset
                LIMIT :limit
                """
            ),
            parameters,
        )
        raw_items = [dict(row) for row in result.mappings().all()]
        total = int(raw_items[0]["catalog_total"]) if raw_items else 0
        items = []
        for item in raw_items:
            item.pop("catalog_total", None)
            items.append(item)
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def answer(self, request: CatalogRequest) -> str:
        if request.action == "unsupported_official_catalog":
            return (
                "VLegal hiện chỉ có thể thống kê trực tiếp dữ liệu trong kho đã index. "
                "Hệ thống chưa được kết nối với catalog pháp luật chính thức để xác nhận tổng số văn bản trên toàn quốc."
            )
        if request.action == "scope_required":
            return (
                "Bạn muốn đếm số Điều trong Bộ luật Lao động 2019 hay số lượng văn bản pháp luật lao động trong kho VLegal?"
            )
        if request.action == "article_count":
            return await self._answer_article_count(request)

        if (
            request.action == "summary"
            and request.document_type is None
            and request.status is None
        ):
            stats = await self.stats()
            type_lines = [
                f"- {CATALOG_TYPES.get(key, key)}: {count}"
                for key, count in sorted(stats["by_type"].items())
                if count
            ]
            status_lines = [
                f"- {STATUS_LABELS.get(key, key)}: {count}"
                for key, count in sorted(stats["by_status"].items())
                if count
            ]
            as_of = stats.get("as_of")
            as_of_text = (
                f" Dữ liệu catalog được làm mới lúc {as_of.isoformat()}."
                if as_of
                else ""
            )
            return (
                f"Kho VLegal hiện có {int(stats['total'])} văn bản đã index."
                " Con số này chỉ phản ánh corpus VLegal, không phải toàn bộ "
                f"hệ thống văn bản pháp luật Việt Nam.{as_of_text}\n\n"
                "Theo loại văn bản:\n"
                + "\n".join(type_lines)
                + "\n\nTheo trạng thái hiệu lực/kiểm chứng:\n"
                + "\n".join(status_lines)
            )
        result = await self.documents(
            document_type=request.document_type,
            status=request.status,
            page=1,
            page_size=20,
        )
        total = int(result["total"])
        type_label = (
            CATALOG_TYPES.get(request.document_type or "", "văn bản")
        )
        status_label = STATUS_LABELS.get(request.status or "", "")
        qualifier = f" {status_label}" if status_label else ""
        as_of = (
            result["items"][0].get("refreshed_at")
            if result["items"]
            else None
        )
        as_of_text = (
            f" Dữ liệu catalog được làm mới lúc {as_of.isoformat()}."
            if as_of
            else ""
        )
        scope_note = (
            " Con số này chỉ phản ánh corpus VLegal đã index, không phải "
            "toàn bộ hệ thống văn bản pháp luật Việt Nam."
        )
        if request.action == "list":
            items = result["items"]
            lines = [
                f"- {item['code']}: {item['title']} "
                f"({STATUS_LABELS.get(item['resolved_status'], item['resolved_status'])})"
                for item in items
            ]
            remainder = (
                f"\n- … và {total - len(items)} văn bản khác."
                if total > len(items)
                else ""
            )
            return (
                f"Kho VLegal hiện có {total} {type_label}{qualifier}."
                f"{scope_note}{as_of_text}\n\n"
                + "\n".join(lines)
                + remainder
            )
        return (
            f"Kho VLegal hiện có {total} {type_label}{qualifier}."
            f"{scope_note}{as_of_text}"
        )

    async def _answer_article_count(self, request: CatalogRequest) -> str:
        """Count Điều for a specific legal document, filtering by law_code.

        Resolution order:
        1. If request.law_code is set → normalize and query directly.
        2. If request.law_name_hint is set → ILIKE title search in legal_catalog_corpus
           to find the law_code_normalized, then query.
        3. If neither is set → ask user to clarify.
        """
        # --- Step 1: resolve law_code_normalized ---
        normalized_code: str | None = None
        resolved_title: str | None = None

        if request.law_code:
            # Normalize the code the same way the index does
            raw = re.sub(r"[\s]+", "", request.law_code.strip()).upper()
            normalized_code = raw
        elif request.law_name_hint:
            # Search by title similarity in legal_catalog_corpus
            hints_to_try = [request.law_name_hint]
            no_year = re.sub(r"\s+\d{4}$", "", request.law_name_hint).strip()
            if no_year != request.law_name_hint:
                hints_to_try.append(no_year)

            for hint in hints_to_try:
                try:
                    res = await self.db.execute(
                        text(
                            """
                            SELECT law_code_normalized,
                                   coalesce(nullif(title, ''), law_code_normalized) AS title
                            FROM legal_catalog_corpus
                            WHERE title ILIKE :pattern
                            ORDER BY law_code_normalized DESC
                            LIMIT 1
                            """
                        ),
                        {"pattern": f"%{hint}%"},
                    )
                    row = res.mappings().all()
                    if row:
                        normalized_code = str(row[0]["law_code_normalized"])
                        resolved_title = str(row[0]["title"])
                        break
                except Exception:
                    pass

        if not normalized_code:
            return (
                "VLegal chưa xác định được văn bản cụ thể bạn hỏi. "
                "Vui lòng cung cấp mã số văn bản (ví dụ: `45/2019/QH14`) để tra chính xác."
            )

        # --- Step 2: count articles filtered by law_code_normalized ---
        try:
            res = await self.db.execute(
                text(
                    """
                    SELECT
                        lc.law_code_normalized,
                        coalesce(nullif(d.title, ''), lc.title) AS title,
                        count(DISTINCT gc.node_id)::bigint AS article_count
                    FROM legal_catalog_corpus AS lc
                    LEFT JOIN legal_document AS d
                        ON upper(
                            regexp_replace(btrim(d.code), '[[:space:]]+', '', 'g')
                        ) = lc.law_code_normalized
                    JOIN graphrag_chunk AS gc
                        ON upper(
                            regexp_replace(btrim(gc.law_code), '[[:space:]]+', '', 'g')
                        ) = lc.law_code_normalized
                    WHERE gc.chunk_type = 'article'
                      AND lc.law_code_normalized = :normalized_code
                    GROUP BY lc.law_code_normalized, coalesce(nullif(d.title, ''), lc.title)
                    """
                ),
                {"normalized_code": normalized_code},
            )
            row = res.mappings().all()
            if row:
                total = int(row[0]["article_count"])
                title = resolved_title or str(row[0]["title"])
                code_display = request.law_code or normalized_code
                return (
                    f"Theo dữ liệu đã index trong kho VLegal, **{title}** "
                    f"(Mã số: `{code_display}`) hiện có tổng cộng **{total} Điều**.\n\n"
                    "*Số liệu phản ánh corpus VLegal đã index, không thay thế văn bản chính thức.*"
                )
            # Văn bản có trong catalog nhưng chưa index chunk
            title = resolved_title or normalized_code
            return (
                f"**{title}** có trong kho VLegal nhưng chưa được index ở dạng từng Điều riêng lẻ. "
                "Số lượng Điều chưa thể thống kê."
            )
        except Exception:
            title = resolved_title or request.law_code or normalized_code or "văn bản này"
            return (
                f"Dữ liệu đếm số Điều của **{title}** tạm thời không truy cập được. "
                "Vui lòng thử lại sau."
            )

    async def _execute(self, statement, parameters=None):
        try:
            return await self.db.execute(statement, parameters or {})
        except Exception as exc:
            message = str(exc).lower()
            if "legal_catalog_corpus" in message:
                raise LegalCatalogUnavailable(
                    "Legal catalogue has not been migrated or refreshed."
                ) from exc
            raise
