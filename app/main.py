from __future__ import annotations

import difflib
import hashlib
import json
import os
import re
import time
import unicodedata
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from groq import Groq
from pydantic import BaseModel, Field

from app.external_graphrag import (
    ExternalGraphRAGConfig,
    Neo4jGraphRAGStore,
    Neo4jQdrantGraphRAGStore,
    QdrantGraphRAGStore,
)
from app.legal_graphrag import GraphRAGStore


APP_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = APP_DIR.parents[0]
STATIC_DIR = APP_DIR / "static"
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"
FRONTEND_ASSETS = FRONTEND_DIST / "assets"
STORAGE_DIR = PROJECT_ROOT / "storage"
GRAPHRAG_DIR = STORAGE_DIR / "graphrag"

load_dotenv(PROJECT_ROOT / ".env", override=True)

app = FastAPI(title="VLegal AI", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
if FRONTEND_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_ASSETS), name="assets")


store_cache: dict[str, Any] = {}
store_backend_errors: dict[str, str] = {}

BACKEND_MODE_LABELS = {
    "qdrant": "RAG",
    "neo4j": "GraphRAG (Neo4j)",
    "hybrid": "Hybrid RAG",
    "sqlite": "Local GraphRAG (SQLite)",
    "unconfigured": "Chưa cấu hình",
}

CONTRACT_TEMPLATES = [
    {"id": "employment", "name": "Hợp đồng lao động", "category": "Lao động"},
    {"id": "probation", "name": "Hợp đồng thử việc", "category": "Lao động"},
    {"id": "nda_salary", "name": "Cam kết bảo mật tiền lương", "category": "Lao động"},
    {"id": "termination", "name": "Quyết định thôi việc", "category": "Lao động"},
    {"id": "service", "name": "Hợp đồng dịch vụ", "category": "Dịch vụ"},
    {"id": "agency", "name": "Hợp đồng đại lý phân phối", "category": "Thương mại"},
    {"id": "lease_office", "name": "Hợp đồng thuê văn phòng", "category": "Bất động sản"},
    {"id": "sale_goods", "name": "Hợp đồng mua bán hàng hóa", "category": "Thương mại"},
    {"id": "loan", "name": "Hợp đồng vay tiền", "category": "Dân sự"},
    {"id": "power_attorney", "name": "Hợp đồng ủy quyền", "category": "Dân sự"},
]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=2, max_length=5000)
    top_k: int = Field(10, ge=3, le=16)
    backend: str | None = None
    law_ids: list[str] = Field(default_factory=list, max_length=10)


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=2)
    top_k: int = Field(10, ge=3, le=20)
    backend: str | None = None


class DraftContractRequest(BaseModel):
    prompt: str = Field(..., min_length=8, max_length=5000)
    template_id: str | None = None
    template_name: str | None = None
    backend: str | None = None
    law_ids: list[str] = Field(default_factory=list, max_length=10)


class ReviewContractRequest(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    text: str = Field(..., min_length=20, max_length=50000)
    backend: str | None = None


class CompareContractRequest(BaseModel):
    original_title: str | None = Field(default=None, max_length=160)
    revised_title: str | None = Field(default=None, max_length=160)
    original_text: str = Field(..., min_length=20, max_length=50000)
    revised_text: str = Field(..., min_length=20, max_length=50000)
    backend: str | None = None


class PrepareSignatureRequest(BaseModel):
    title: str = Field(..., min_length=2, max_length=180)
    document_text: str = Field(..., min_length=5, max_length=50000)
    signers: list[str] = Field(default_factory=list, max_length=10)


class FeedbackRequest(BaseModel):
    message: str = Field(..., min_length=3, max_length=2000)
    email: str | None = Field(default=None, max_length=180)
    page: str | None = Field(default=None, max_length=120)


def normalize_backend(value: str | None) -> str:
    backend = (
        value or os.getenv("RETRIEVER_BACKEND", "auto")
    ).strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "external": "hybrid",
        "hybrid_rag": "hybrid",
        "hybridrag": "hybrid",
        "neo4j_qdrant": "hybrid",
        "neo4j+qdrant": "hybrid",
        "neo4j_qdrant_rag": "hybrid",
        "rag": "qdrant",
        "basic_rag": "qdrant",
        "vector": "qdrant",
        "vector_rag": "qdrant",
        "qdrant_cloud": "qdrant",
        "qdrant_rag": "qdrant",
        "graph": "neo4j",
        "graph_rag": "neo4j",
        "graphrag": "neo4j",
        "neo4j_rag": "neo4j",
        "sqlite": "sqlite",
        "sqlite_rag": "sqlite",
        "local": "sqlite",
        "local_graphrag": "sqlite",
        "local-graphrag": "sqlite",
    }
    return aliases.get(backend, backend)


def backend_mode_label(backend: str) -> str:
    return BACKEND_MODE_LABELS.get(backend, backend)


def backend_candidates(value: str | None, config: ExternalGraphRAGConfig) -> list[str]:
    backend = normalize_backend(value)
    if backend != "auto":
        return [backend]
    candidates: list[str] = []
    if config.ready:
        candidates.append("hybrid")
    if config.qdrant_ready:
        candidates.append("qdrant")
    if config.neo4j_ready:
        candidates.append("neo4j")
    candidates.append("sqlite")
    return candidates or ["unconfigured"]


def resolve_backend(value: str | None, config: ExternalGraphRAGConfig) -> str:
    return backend_candidates(value, config)[0]


def get_store(backend_override: str | None = None) -> Any:
    config = ExternalGraphRAGConfig.from_env()
    requested = normalize_backend(backend_override)
    errors: list[str] = []
    for backend in backend_candidates(backend_override, config):
        if backend in store_cache:
            return store_cache[backend]
        try:
            if backend == "hybrid":
                store_cache[backend] = Neo4jQdrantGraphRAGStore(config)
            elif backend == "qdrant":
                store_cache[backend] = QdrantGraphRAGStore(config)
            elif backend == "neo4j":
                store_cache[backend] = Neo4jGraphRAGStore(config)
            elif backend == "sqlite":
                store_cache[backend] = GraphRAGStore()
            elif backend == "unconfigured":
                raise RuntimeError(
                    "No external backend is configured. Set QDRANT_URL/QDRANT_API_KEY and/or NEO4J_PASSWORD."
                )
            else:
                raise RuntimeError(f"Unsupported RETRIEVER_BACKEND: {backend}")
            store_backend_errors.pop(backend, None)
            return store_cache[backend]
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            store_backend_errors[backend] = error
            errors.append(f"{backend}: {error}")
            if requested != "auto":
                break
    raise HTTPException(
        status_code=503,
        detail="No configured retrieval backend is ready. " + " | ".join(errors),
    )


def text_quality(value: str) -> int:
    broken_markers = ("Ã", "Â", "Æ", "Ä", "á»", "áº", "â€", "ï¿½", "\ufffd")
    vietnamese = "ăâđêôơưáàảãạắằẳẵặấầẩẫậéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
    broken = sum(value.count(marker) for marker in broken_markers)
    vn_count = sum(1 for char in value.lower() if char in vietnamese)
    replacement = value.count("?") + value.count("\ufffd")
    return vn_count * 3 - broken * 8 - replacement * 10


def repair_text(value: Any) -> str:
    if value is None:
        return ""
    current = str(value)
    for _ in range(3):
        candidates = [current]
        for encoding in ("latin1", "cp1252"):
            try:
                candidates.append(current.encode(encoding).decode("utf-8"))
            except UnicodeError:
                continue
        best = max(candidates, key=text_quality)
        if best == current:
            break
        current = best
    return current


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", repair_text(text).replace("\xa0", " ")).strip()


def fold_text(text: str) -> str:
    text = repair_text(text).replace("đ", "d").replace("Đ", "D")
    return "".join(
        char for char in unicodedata.normalize("NFD", text.lower())
        if unicodedata.category(char) != "Mn"
    )


def compact_text(text: str, limit: int = 1400) -> str:
    text = normalize_space(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def build_context(sources: list[dict[str, Any]], max_chars: int = 14000) -> str:
    blocks: list[str] = []
    used = 0
    for source in sources:
        snippet = compact_text(source.get("text", ""), 1800)
        block = f"[{source.get('source_id')}] {repair_text(source.get('citation') or source.get('title'))}\n{snippet}"
        if used + len(block) > max_chars:
            break
        blocks.append(block)
        used += len(block)
    return "\n\n".join(blocks)


def selected_law_context(law_ids: list[str]) -> tuple[list[dict[str, Any]], str]:
    if not law_ids:
        return [], ""
    catalog = {law["id"]: law for law in law_catalog()}
    selected = [catalog[law_id] for law_id in law_ids if law_id in catalog][:10]
    if not selected:
        return [], ""
    lines = [f"- {law['code']}: {law['title']}" for law in selected]
    return selected, "Văn bản ưu tiên:\n" + "\n".join(lines)


def fallback_answer(message: str, sources: list[dict[str, Any]], mode_label: str) -> str:
    if not sources:
        return f"Chưa tìm thấy căn cứ phù hợp trong chế độ {mode_label}."
    lines = [
        f"Chưa cấu hình `GROQ_API_KEY`, nên hệ thống trả về kết quả truy xuất {mode_label} thay vì câu trả lời LLM.",
        "",
        "Các căn cứ liên quan nhất:",
    ]
    for source in sources[:5]:
        lines.append(f"- [{source['source_id']}] {source['citation']}: {compact_text(source['text'], 360)}")
    return "\n".join(lines)


def groq_completion(system_prompt: str, user_prompt: str, max_tokens: int = 1500, temperature: float = 0.12) -> str | None:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    client = Groq(api_key=api_key)
    completion = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return completion.choices[0].message.content or ""


def call_groq_chat(message: str, sources: list[dict[str, Any]], mode_label: str, laws_block: str = "") -> str:
    if not sources:
        return f"Tôi chưa tìm thấy căn cứ đủ rõ trong chế độ {mode_label} để trả lời chắc chắn."
    context = build_context(sources)
    system_prompt = (
        "Bạn là VLegal AI, trợ lý pháp lý Việt Nam. Chỉ sử dụng CONTEXT được cung cấp, không bịa căn cứ. "
        "Khi trả lời, trích dẫn nguồn bằng ký hiệu [S1], [S2] ngay sau luận điểm liên quan. "
        "Nếu context chưa đủ, nói rõ phần nào chưa đủ căn cứ. Trả lời ngắn gọn, có cấu trúc, dễ hiểu. "
        "Không thay thế tư vấn pháp lý của luật sư trong vụ việc cụ thể."
    )
    user_prompt = f"{laws_block}\n\nCONTEXT:\n{context}\n\nCÂU HỎI:\n{message}".strip()
    answer = groq_completion(system_prompt, user_prompt, max_tokens=1300, temperature=0.1)
    return answer if answer is not None else fallback_answer(message, sources, mode_label)


def retrieve_with_fallback(query: str, top_k: int, backend: str | None = None) -> tuple[list[dict[str, Any]], str]:
    selected_backend = resolve_backend(backend, ExternalGraphRAGConfig.from_env())
    try:
        store = get_store(backend)
    except Exception:
        selected_backend = "sqlite"
        store = get_store("sqlite")
    return store.retrieve(query, top_k), selected_backend


def serialize_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    serialized = []
    for source in sources:
        serialized.append(
            {
                "source_id": source.get("source_id", ""),
                "score": source.get("score", 0),
                "chunk_type": repair_text(source.get("chunk_type", "")),
                "citation": compact_text(source.get("citation") or source.get("title") or "Nguồn pháp lý", 320),
                "title": compact_text(source.get("title") or "", 220),
                "text": compact_text(source.get("text") or "", 1200),
                "reasons": [repair_text(reason) for reason in source.get("reasons", [])],
            }
        )
    return serialized


@lru_cache(maxsize=1)
def law_catalog() -> list[dict[str, Any]]:
    path = GRAPHRAG_DIR / "documents.jsonl"
    laws: list[dict[str, Any]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                code = compact_text(row.get("code") or row.get("filename") or row.get("doc_id"), 80)
                title = compact_text(row.get("title") or row.get("filename") or code, 260)
                laws.append(
                    {
                        "id": repair_text(row.get("doc_id") or code),
                        "code": code,
                        "title": title,
                        "doc_type": compact_text(row.get("doc_type") or "Văn bản", 80),
                        "issuer": compact_text(row.get("issuer") or "Cơ quan nhà nước", 100),
                    }
                )
    if laws:
        return laws
    return [
        {
            "id": "bo-luat-lao-dong-2019",
            "code": "45/2019/QH14",
            "title": "Bộ luật Lao động 2019",
            "doc_type": "Bộ luật",
            "issuer": "Quốc hội",
        },
        {
            "id": "nghi-dinh-145-2020",
            "code": "145/2020/NĐ-CP",
            "title": "Nghị định hướng dẫn Bộ luật Lao động về điều kiện lao động và quan hệ lao động",
            "doc_type": "Nghị định",
            "issuer": "Chính phủ",
        },
    ]


def template_name(template_id: str | None, explicit_name: str | None = None) -> str:
    if explicit_name:
        return explicit_name
    for template in CONTRACT_TEMPLATES:
        if template["id"] == template_id:
            return template["name"]
    return "Văn bản pháp lý"


def fallback_contract_draft(prompt: str, template: str, sources: list[dict[str, Any]]) -> str:
    citations = ", ".join(f"[{source['source_id']}]" for source in sources[:3]) or "căn cứ pháp luật liên quan"
    return f"""# {template.upper()}

## 1. Thông tin các bên
- Bên A: [Tên, mã số thuế/CCCD, địa chỉ, người đại diện]
- Bên B: [Tên, mã số thuế/CCCD, địa chỉ, người đại diện]

## 2. Bối cảnh và mục đích
Văn bản này được lập theo yêu cầu: "{compact_text(prompt, 260)}".

## 3. Nội dung thỏa thuận chính
1. Phạm vi công việc/quyền và nghĩa vụ của các bên cần được mô tả cụ thể.
2. Thời hạn thực hiện, địa điểm, cách bàn giao và nghiệm thu cần ghi rõ.
3. Giá trị thanh toán, thời điểm thanh toán, chứng từ và nghĩa vụ thuế cần được xác định riêng.

## 4. Điều khoản tuân thủ pháp luật
Các bên cam kết thực hiện đúng quy định pháp luật Việt Nam, các quy định chuyên ngành có liên quan và các căn cứ đã truy xuất: {citations}.

## 5. Vi phạm, chấm dứt và giải quyết tranh chấp
- Bên vi phạm phải khắc phục trong thời hạn [x] ngày kể từ ngày nhận thông báo.
- Trường hợp không khắc phục, bên bị vi phạm có quyền tạm ngừng hoặc chấm dứt văn bản theo thỏa thuận và pháp luật.
- Tranh chấp được ưu tiên thương lượng; nếu không thành, chuyển tới cơ quan có thẩm quyền tại Việt Nam.

## 6. Điều khoản cuối
Văn bản có hiệu lực từ ngày ký và được lập thành [x] bản có giá trị pháp lý như nhau.

> Đây là bản nháp tự động. Cần bổ sung dữ kiện thực tế, kiểm tra điều kiện ngành nghề và rà soát bởi luật sư trước khi ký."""


def contract_checklist(template: str) -> list[str]:
    base = [
        "Điền đầy đủ thông tin định danh của các bên.",
        "Xác định rõ đối tượng, phạm vi, thời hạn và địa điểm thực hiện.",
        "Bổ sung điều khoản thanh toán, thuế, hóa đơn và nghiệm thu.",
        "Kiểm tra thẩm quyền ký và tài liệu ủy quyền nếu có.",
        "Rà soát điều khoản chấm dứt, phạt vi phạm, bồi thường và giải quyết tranh chấp.",
    ]
    if "lao động" in fold_text(template):
        base.insert(2, "Kiểm tra loại hợp đồng, thời giờ làm việc, tiền lương, BHXH, ngày nghỉ và thử việc.")
    return base


def detect_contract_risks(text: str) -> list[dict[str, str]]:
    normalized = fold_text(text)
    checks = [
        (
            "medium",
            "Thiếu điều khoản thanh toán rõ ràng",
            ["thanh toan", "gia tri", "phi", "luong"],
            "Bổ sung số tiền, thời hạn, phương thức thanh toán, chứng từ và hậu quả khi chậm thanh toán.",
        ),
        (
            "high",
            "Chưa thấy cơ chế chấm dứt/đơn phương",
            ["cham dut", "don phuong", "huy bo"],
            "Quy định rõ căn cứ chấm dứt, thời hạn báo trước, nghĩa vụ bàn giao và thanh toán khi chấm dứt.",
        ),
        (
            "medium",
            "Thiếu cơ chế giải quyết tranh chấp",
            ["tranh chap", "toa an", "trong tai", "thuong luong"],
            "Thêm bước thương lượng, cơ quan giải quyết, luật áp dụng và địa điểm giải quyết tranh chấp.",
        ),
        (
            "medium",
            "Thiếu điều khoản bảo mật/dữ liệu",
            ["bao mat", "du lieu", "thong tin"],
            "Nếu có trao đổi dữ liệu hoặc bí mật kinh doanh, cần thêm phạm vi bảo mật, thời hạn và chế tài.",
        ),
        (
            "low",
            "Chưa thấy điều khoản bất khả kháng",
            ["bat kha khang", "thien tai", "dich benh"],
            "Bổ sung sự kiện bất khả kháng, nghĩa vụ thông báo và cách xử lý khi kéo dài.",
        ),
    ]
    risks: list[dict[str, str]] = []
    for level, title, keywords, recommendation in checks:
        if not any(keyword in normalized for keyword in keywords):
            risks.append(
                {
                    "level": level,
                    "title": title,
                    "detail": "Không tìm thấy nhóm nội dung này trong văn bản được cung cấp.",
                    "recommendation": recommendation,
                }
            )
    if "phat vi pham" in normalized and "boi thuong" not in normalized:
        risks.append(
            {
                "level": "medium",
                "title": "Có phạt vi phạm nhưng chưa thấy bồi thường thiệt hại",
                "detail": "Điều khoản phạt vi phạm nên đi cùng cơ chế chứng minh và bồi thường thiệt hại nếu có.",
                "recommendation": "Tách rõ phạt vi phạm, bồi thường thiệt hại, giới hạn trách nhiệm và trường hợp miễn trách.",
            }
        )
    return risks[:8]


def summarize_differences(original_text: str, revised_text: str) -> list[dict[str, str]]:
    original_lines = [normalize_space(line) for line in original_text.splitlines() if normalize_space(line)]
    revised_lines = [normalize_space(line) for line in revised_text.splitlines() if normalize_space(line)]
    matcher = difflib.SequenceMatcher(a=original_lines, b=revised_lines)
    differences: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        before = " ".join(original_lines[i1:i2])[:420]
        after = " ".join(revised_lines[j1:j2])[:420]
        differences.append(
            {
                "type": {
                    "replace": "Sửa đổi",
                    "delete": "Bị xóa",
                    "insert": "Bổ sung",
                }.get(tag, tag),
                "before": before or "Không có",
                "after": after or "Không có",
            }
        )
        if len(differences) >= 10:
            break
    return differences


@app.get("/")
def index() -> FileResponse:
    if (FRONTEND_DIST / "index.html").exists():
        return FileResponse(FRONTEND_DIST / "index.html")
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/stats")
def stats(backend: str | None = None) -> dict[str, Any]:
    selected_backend = resolve_backend(backend, ExternalGraphRAGConfig.from_env())
    try:
        data = get_store(backend).stats()
    except Exception as exc:
        selected_backend = "sqlite"
        data = get_store("sqlite").stats()
        data["backend_error"] = f"Không kết nối được external backend. Đang dùng Local SQLite. Lỗi: {exc}"

    data.setdefault("backend", selected_backend)
    data["selected_backend"] = selected_backend
    data["mode_label"] = backend_mode_label(selected_backend)
    data["retrieval_modes"] = [
        {"value": "rag", "backend": "qdrant", "label": "RAG"},
        {"value": "graphrag", "backend": "neo4j", "label": "GraphRAG (Neo4j)"},
        {"value": "hybrid_rag", "backend": "hybrid", "label": "Hybrid RAG"},
        {"value": "local_graphrag", "backend": "sqlite", "label": "Local GraphRAG"},
    ]
    if "backend_error" not in data and selected_backend in store_backend_errors:
        data["backend_error"] = store_backend_errors[selected_backend]
    data["groq_ready"] = bool(os.getenv("GROQ_API_KEY"))
    data["groq_model"] = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    return data


@app.get("/api/laws/search")
def search_laws(q: str = "", limit: int = 50, offset: int = 0) -> dict[str, Any]:
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    query = fold_text(q)
    rows = law_catalog()
    if query:
        scored = []
        tokens = [token for token in query.split() if len(token) >= 2]
        for law in rows:
            haystack = fold_text(f"{law['code']} {law['title']} {law['doc_type']} {law['issuer']}")
            score = 0
            if query in haystack:
                score += 10
            score += sum(2 for token in tokens if token in haystack)
            if score:
                scored.append((score, law))
        scored.sort(key=lambda item: (-item[0], len(item[1]["title"])))
        rows = [law for _, law in scored]
    else:
        rows = rows[:200]
    return {"query": q, "total": len(rows), "items": rows[offset : offset + limit]}


@app.get("/api/templates")
def templates() -> dict[str, Any]:
    categories = sorted({template["category"] for template in CONTRACT_TEMPLATES})
    return {"categories": categories, "templates": CONTRACT_TEMPLATES}


@app.post("/api/search")
def search(request: SearchRequest) -> dict[str, Any]:
    sources, selected_backend = retrieve_with_fallback(request.query, request.top_k, request.backend)
    return {
        "query": request.query,
        "backend": selected_backend,
        "mode_label": backend_mode_label(selected_backend),
        "sources": serialize_sources(sources),
    }


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict[str, Any]:
    selected_laws, laws_block = selected_law_context(request.law_ids)
    retrieval_query = request.message
    if selected_laws:
        retrieval_query = f"{request.message}\n" + "\n".join(
            f"{law['code']} {law['title']}" for law in selected_laws
        )
    sources, selected_backend = retrieve_with_fallback(retrieval_query, request.top_k, request.backend)
    mode_label = backend_mode_label(selected_backend)
    try:
        answer = call_groq_chat(request.message, sources, mode_label, laws_block)
    except Exception as exc:
        answer = (
            f"LLM chưa trả lời được trong lần gọi này ({type(exc).__name__}). "
            f"Dưới đây là các căn cứ {mode_label} đã truy xuất.\n\n"
            + fallback_answer(request.message, sources, mode_label)
        )
    return {
        "answer": answer,
        "backend": selected_backend,
        "mode_label": mode_label,
        "sources": serialize_sources(sources),
        "selected_laws": selected_laws,
        "groq_ready": bool(os.getenv("GROQ_API_KEY")),
    }


@app.post("/api/contracts/draft")
def draft_contract(request: DraftContractRequest) -> dict[str, Any]:
    template = template_name(request.template_id, request.template_name)
    selected_laws, laws_block = selected_law_context(request.law_ids)
    retrieval_query = f"Soạn {template}. {request.prompt} {laws_block}"
    sources, selected_backend = retrieve_with_fallback(retrieval_query, 8, request.backend)
    system_prompt = (
        "Bạn là trợ lý soạn thảo văn bản pháp lý Việt Nam. Dựa trên CONTEXT, tạo bản nháp rõ cấu trúc, "
        "để placeholder trong ngoặc vuông khi thiếu dữ kiện. Không bịa căn cứ, không cam kết văn bản đã đủ điều kiện ký."
    )
    user_prompt = (
        f"Loại văn bản: {template}\nYêu cầu: {request.prompt}\n{laws_block}\n\n"
        f"CONTEXT:\n{build_context(sources, 10000)}"
    )
    try:
        draft = groq_completion(system_prompt, user_prompt, max_tokens=2200, temperature=0.18)
    except Exception:
        draft = None
    if not draft:
        draft = fallback_contract_draft(request.prompt, template, serialize_sources(sources))
    return {
        "title": template,
        "draft": draft,
        "checklist": contract_checklist(template),
        "backend": selected_backend,
        "mode_label": backend_mode_label(selected_backend),
        "sources": serialize_sources(sources),
        "selected_laws": selected_laws,
    }


@app.post("/api/contracts/review")
def review_contract(request: ReviewContractRequest) -> dict[str, Any]:
    query = f"Rà soát rủi ro hợp đồng: {request.title or ''} {request.text[:1600]}"
    sources, selected_backend = retrieve_with_fallback(query, 8, request.backend)
    risks = detect_contract_risks(request.text)
    system_prompt = (
        "Bạn là trợ lý rà soát hợp đồng Việt Nam. Dựa trên CONTEXT và văn bản người dùng, "
        "tóm tắt rủi ro chính, điều khoản cần sửa và căn cứ liên quan. Trả lời ngắn gọn theo markdown."
    )
    user_prompt = f"Văn bản:\n{request.text[:12000]}\n\nCONTEXT:\n{build_context(sources, 9000)}"
    ai_summary = None
    try:
        ai_summary = groq_completion(system_prompt, user_prompt, max_tokens=1400, temperature=0.1)
    except Exception:
        ai_summary = None
    summary = ai_summary or (
        "Hệ thống đã rà soát theo các nhóm rủi ro thường gặp. "
        f"Phát hiện {len(risks)} điểm cần kiểm tra thêm trước khi sử dụng văn bản."
    )
    recommendations = [
        "Đối chiếu lại thẩm quyền ký và thông tin pháp lý của các bên.",
        "Bổ sung phụ lục hoặc bảng mô tả công việc nếu đối tượng hợp đồng chưa rõ.",
        "Đưa các mốc thanh toán, bàn giao, nghiệm thu vào cùng một bảng để dễ kiểm soát.",
    ]
    return {
        "summary": summary,
        "risks": risks,
        "recommendations": recommendations,
        "backend": selected_backend,
        "mode_label": backend_mode_label(selected_backend),
        "sources": serialize_sources(sources),
    }


@app.post("/api/contracts/compare")
def compare_contracts(request: CompareContractRequest) -> dict[str, Any]:
    query = f"So sánh hợp đồng, rủi ro khi sửa đổi: {request.original_text[:800]} {request.revised_text[:800]}"
    sources, selected_backend = retrieve_with_fallback(query, 6, request.backend)
    differences = summarize_differences(request.original_text, request.revised_text)
    revised_risks = detect_contract_risks(request.revised_text)
    similarity = difflib.SequenceMatcher(None, request.original_text, request.revised_text).ratio()
    return {
        "summary": (
            f"Hai phiên bản giống nhau khoảng {round(similarity * 100)}%. "
            f"Hệ thống tìm thấy {len(differences)} nhóm thay đổi nổi bật và {len(revised_risks)} điểm cần rà soát ở bản mới."
        ),
        "differences": differences,
        "risks": revised_risks[:5],
        "recommendation": "Ưu tiên kiểm tra các phần bị sửa về thanh toán, chấm dứt, phạt vi phạm, bảo mật và thẩm quyền ký.",
        "backend": selected_backend,
        "mode_label": backend_mode_label(selected_backend),
        "sources": serialize_sources(sources),
    }


@app.post("/api/signatures/prepare")
def prepare_signature(request: PrepareSignatureRequest) -> dict[str, Any]:
    normalized_signers = [normalize_space(signer) for signer in request.signers if normalize_space(signer)]
    document_hash = hashlib.sha256(
        f"{request.title}\n{request.document_text}\n{'|'.join(normalized_signers)}".encode("utf-8")
    ).hexdigest()
    packet_id = f"sig-{uuid.uuid4().hex[:12]}"
    created_at = int(time.time())
    audit_log = [
        {"time": created_at, "event": "Tạo gói ký", "actor": "VLegal AI"},
        {"time": created_at, "event": f"Băm SHA-256 tài liệu: {document_hash[:16]}...", "actor": "Hệ thống"},
    ]
    return {
        "signature_id": packet_id,
        "title": request.title,
        "status": "ready",
        "document_hash": document_hash,
        "signers": normalized_signers,
        "audit_log": audit_log,
        "next_steps": [
            "Kiểm tra lại bản cuối trước khi gửi ký.",
            "Xác thực danh tính người ký theo quy trình nội bộ.",
            "Lưu gói ký và nhật ký thao tác cùng hồ sơ giao dịch.",
        ],
    }


@app.post("/api/feedback")
def feedback(request: FeedbackRequest) -> dict[str, Any]:
    logs_dir = STORAGE_DIR / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    payload = request.model_dump()
    payload["created_at"] = int(time.time())
    with (logs_dir / "feedback.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return {"ok": True}


@app.get("/{full_path:path}")
def spa_fallback(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="Not found")
    if (FRONTEND_DIST / "index.html").exists():
        return FileResponse(FRONTEND_DIST / "index.html")
    return FileResponse(STATIC_DIR / "index.html")
