from __future__ import annotations

import hashlib
import io
import re
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup
from docx import Document
from fastapi.concurrency import run_in_threadpool
from neo4j import GraphDatabase
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.external_graphrag import (
    ExternalGraphRAGConfig,
    ensure_neo4j_schema,
    ensure_qdrant_collection,
    qdrant_dense_vector,
)
from app.models import LegalChunk, LegalDocument


ARTICLE_RE = re.compile(r"(?im)^\s*(Điều\s+\d+[a-zA-Z]?[\.:]?\s*[^\n]*)")
CLAUSE_RE = re.compile(r"(?m)^\s*(\d+)\.\s+")


@dataclass(slots=True)
class LegalCandidate:
    code: str
    title: str
    url: str
    status: str
    issuer: str = ""
    external_doc_id: str | None = None
    replaces_code: str | None = None
    content: str | None = None


def _clean_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def _extract_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def _extract_docx(content: bytes) -> str:
    document = Document(io.BytesIO(content))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _extract_html(content: bytes) -> str:
    soup = BeautifulSoup(content, "html.parser")
    for node in soup(["script", "style", "nav", "footer", "form", "noscript"]):
        node.decompose()
    root = soup.find("article") or soup.find("main") or soup.body or soup
    return root.get_text("\n", strip=True)


async def download_legal_text(url: str, timeout: int = 45) -> tuple[str, str]:
    headers = {"User-Agent": "VLegalAI/3.0 (+legal-document-refresh)"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, headers=headers) as client:
        response = await client.get(url)
        response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    suffix = urlparse(str(response.url)).path.lower()
    if "pdf" in content_type or suffix.endswith(".pdf"):
        text = await run_in_threadpool(_extract_pdf, response.content)
    elif "word" in content_type or suffix.endswith(".docx"):
        text = await run_in_threadpool(_extract_docx, response.content)
    else:
        text = await run_in_threadpool(_extract_html, response.content)
    cleaned = _clean_text(text)
    if len(cleaned) < 500:
        raise ValueError("Nguồn chính thức không có đủ nội dung để tạo chỉ mục")
    return cleaned, str(response.url)


def chunk_legal_text(candidate: LegalCandidate, text: str, version: int) -> list[dict[str, Any]]:
    matches = list(ARTICLE_RE.finditer(text))
    sections: list[tuple[str, str]] = []
    if matches:
        preamble = text[: matches[0].start()].strip()
        if preamble:
            sections.append((candidate.title, preamble))
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            sections.append((match.group(1).strip(), text[match.start() : end].strip()))
    else:
        size, overlap = 3500, 350
        cursor = 0
        while cursor < len(text):
            sections.append((f"Phần {len(sections) + 1}", text[cursor : cursor + size].strip()))
            cursor += size - overlap

    chunks: list[dict[str, Any]] = []
    ordinal = 0
    for heading, section in sections:
        parts = [section]
        if len(section) > 5500:
            clause_starts = list(CLAUSE_RE.finditer(section))
            if len(clause_starts) > 1:
                parts = []
                for idx, match in enumerate(clause_starts):
                    end = clause_starts[idx + 1].start() if idx + 1 < len(clause_starts) else len(section)
                    parts.append(section[match.start() : end].strip())
        for part in parts:
            if not part:
                continue
            chunk_key = f"{candidate.code}:{version}:{ordinal}:{hashlib.sha256(part.encode('utf-8')).hexdigest()[:12]}"
            node_id = f"law:{candidate.code}:v{version}:section:{ordinal}"
            chunks.append(
                {
                    "external_chunk_id": chunk_key,
                    "node_id": node_id,
                    "chunk_type": "article" if heading.lower().startswith("điều") else "section",
                    "title": candidate.title,
                    "citation": f"{candidate.code} — {heading}",
                    "text": part,
                    "text_hash": hashlib.sha256(part.encode("utf-8")).hexdigest(),
                    "ordinal": ordinal,
                }
            )
            ordinal += 1
    return chunks


class LegalIndexer:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _external_config(self) -> ExternalGraphRAGConfig:
        return ExternalGraphRAGConfig(
            neo4j_uri=self.settings.neo4j_uri,
            neo4j_user=self.settings.neo4j_user,
            neo4j_password=self.settings.neo4j_password,
            neo4j_database=self.settings.neo4j_database,
            qdrant_url=self.settings.qdrant_url,
            qdrant_api_key=self.settings.qdrant_api_key,
            qdrant_collection=self.settings.qdrant_collection,
            qdrant_vector_name=self.settings.qdrant_vector_name,
            qdrant_vector_size=self.settings.qdrant_vector_size,
        )

    async def index_candidate(self, db: AsyncSession, candidate: LegalCandidate) -> LegalDocument:
        host = (urlparse(candidate.url).hostname or "").lower()
        if not any(host == domain or host.endswith(f".{domain}") for domain in self.settings.official_legal_domains):
            raise ValueError("Từ chối tải văn bản từ tên miền không thuộc danh sách nguồn chính thức")
        try:
            text, resolved_url = await download_legal_text(candidate.url)
        except (httpx.HTTPError, ValueError):
            if not candidate.content or len(_clean_text(candidate.content)) < 500:
                raise
            text, resolved_url = _clean_text(candidate.content), candidate.url
        checksum = hashlib.sha256(text.encode("utf-8")).hexdigest()
        document = await db.scalar(select(LegalDocument).where(LegalDocument.code == candidate.code))
        if document and document.checksum == checksum:
            document.status = candidate.status
            document.source_url = resolved_url
            return document
        if not document:
            document = LegalDocument(
                code=candidate.code,
                title=candidate.title,
                issuer=candidate.issuer or None,
                external_doc_id=candidate.external_doc_id,
                source_url=resolved_url,
                official_domain=urlparse(resolved_url).netloc.lower(),
                status=candidate.status,
                checksum=checksum,
                version=1,
            )
            db.add(document)
            await db.flush()
        else:
            if document.checksum:
                document.version += 1
            document.title = candidate.title or document.title
            document.external_doc_id = document.external_doc_id or candidate.external_doc_id
            document.source_url = resolved_url
            document.official_domain = urlparse(resolved_url).netloc.lower()
            document.status = candidate.status
            document.checksum = checksum

        chunks = chunk_legal_text(candidate, text, document.version)
        await db.execute(
            delete(LegalChunk).where(LegalChunk.document_id == document.id, LegalChunk.version == document.version)
        )
        rows: list[LegalChunk] = []
        for chunk in chunks:
            point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"vlegal:{chunk['external_chunk_id']}"))
            row = LegalChunk(
                document_id=document.id,
                version=document.version,
                qdrant_point_id=point_id,
                **chunk,
            )
            db.add(row)
            rows.append(row)
        await db.flush()
        await run_in_threadpool(self._sync_external, document, rows, candidate.replaces_code)
        return document

    def _sync_external(
        self, document: LegalDocument, chunks: list[LegalChunk], replaces_code: str | None
    ) -> None:
        config = self._external_config()
        if config.qdrant_url:
            client = QdrantClient(url=config.qdrant_url, api_key=config.qdrant_api_key or None, timeout=60)
            ensure_qdrant_collection(client, config)
            points = []
            for chunk in chunks:
                payload = {
                    "chunk_id": chunk.external_chunk_id,
                    "doc_id": document.external_doc_id or str(document.id),
                    "node_id": chunk.node_id,
                    "chunk_type": chunk.chunk_type,
                    "title": chunk.title,
                    "path_label": chunk.citation,
                    "citation": chunk.citation,
                    "text": chunk.text,
                    "token_count": len(chunk.text.split()),
                    "ordinal": chunk.ordinal,
                    "source_url": document.source_url,
                    "law_code": document.code,
                    "law_status": document.status,
                    "law_version": document.version,
                }
                vector_text = f"{chunk.title}\n{chunk.citation}\n{chunk.text}"
                points.append(
                    PointStruct(
                        id=chunk.qdrant_point_id,
                        vector={config.qdrant_vector_name: qdrant_dense_vector(vector_text, config)},
                        payload=payload,
                    )
                )
            for offset in range(0, len(points), 128):
                client.upsert(config.qdrant_collection, points=points[offset : offset + 128], wait=True)

        if config.neo4j_password:
            driver = GraphDatabase.driver(config.neo4j_uri, auth=(config.neo4j_user, config.neo4j_password))
            try:
                ensure_neo4j_schema(driver, config.neo4j_database)
                with driver.session(database=config.neo4j_database) as session:
                    session.run(
                        """
                        MERGE (d:LegalNode {node_id: $node_id})
                        SET d.node_type='document', d.doc_id=$doc_id, d.code=$code,
                            d.title=$title, d.status=$status, d.source_url=$source_url, d.version=$version
                        """,
                        node_id=f"law:{document.code}:v{document.version}",
                        doc_id=document.external_doc_id or str(document.id),
                        code=document.code,
                        title=document.title,
                        status=document.status,
                        source_url=document.source_url,
                        version=document.version,
                    )
                    session.run(
                        """
                        UNWIND $rows AS row
                        MERGE (n:LegalNode {node_id: row.node_id})
                        SET n.node_type=row.chunk_type, n.doc_id=$doc_id, n.title=row.citation,
                            n.text=row.text, n.ordinal=row.ordinal
                        MERGE (c:LegalChunk {chunk_id: row.chunk_id})
                        SET c.node_id=row.node_id, c.doc_id=$doc_id, c.chunk_type=row.chunk_type,
                            c.title=$title, c.citation=row.citation, c.text=row.text,
                            c.ordinal=row.ordinal, c.source_url=$source_url, c.version=$version
                        MERGE (c)-[:CHUNK_OF]->(n)
                        MERGE (n)-[:BELONGS_TO]->(d)
                        """,
                        rows=[
                            {
                                "node_id": chunk.node_id,
                                "chunk_id": chunk.external_chunk_id,
                                "chunk_type": chunk.chunk_type,
                                "citation": chunk.citation,
                                "text": chunk.text,
                                "ordinal": chunk.ordinal,
                            }
                            for chunk in chunks
                        ],
                        doc_id=document.external_doc_id or str(document.id),
                        title=document.title,
                        source_url=document.source_url,
                        version=document.version,
                    )
                    if replaces_code:
                        session.run(
                            """
                            MATCH (new:LegalNode {node_id: $new_id})
                            MATCH (old:LegalNode) WHERE old.code = $old_code
                            MERGE (new)-[:REPLACES]->(old)
                            """,
                            new_id=f"law:{document.code}:v{document.version}",
                            old_code=replaces_code,
                        )
            finally:
                driver.close()
