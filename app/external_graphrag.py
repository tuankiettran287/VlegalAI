from __future__ import annotations

from collections import Counter
import json
import logging
import math
import os
import re
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

from neo4j import GraphDatabase
import psycopg
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from app.legal_graphrag import DEFAULT_DB_PATH, blob_to_vector, key_terms, normalize_space, strip_accents
from app.legal_ontology import RELATIONS as LEGAL_RELATIONS
from app.legal_ontology import REVERSIBLE_RELATIONS as LEGAL_REVERSIBLE_RELATIONS
from app.services.embeddings import (
    EmbeddingConfig,
    get_embedding_service,
    parse_vertex_locations,
)


logger = logging.getLogger(__name__)


#: Accent-stripped Vietnamese relation -> Neo4j relationship type.
#: Derived from ``app.legal_ontology.RELATIONS`` so the two stay in step; the
#: literal spellings below are the accent-stripped forms produced by
#: ``relation_type()`` at sync time.
RELATION_TYPE_MAP = {
    strip_accents(relation).upper(): english
    for relation, (english, _layer, _weight, _doc) in LEGAL_RELATIONS.items()
}
#: Relations emitted by older index builds, kept so a stale SQLite snapshot
#: still syncs into Neo4j with a meaningful type instead of RELATED_TO.
RELATION_TYPE_MAP.update(
    {
        "BI_NAM_TRONG_DANH_MUC_CAM": "PROHIBITED_BY",
        "GIAI_DOAN_TIEP_THEO": "NEXT_STAGE",
    }
)

GRAPH_EXPAND_RELS = sorted(
    {english for english, _layer, _weight, _doc in LEGAL_RELATIONS.values()} - {"ISSUED_BY"}
)
GRAPH_REVERSE_RELS = sorted(
    {
        LEGAL_RELATIONS[relation][0]
        for relation in LEGAL_REVERSIBLE_RELATIONS
        if relation in LEGAL_RELATIONS
    }
)
#: Expansion weights keyed by Neo4j relationship type.
GRAPH_RELATION_WEIGHTS = {
    english: weight for english, _layer, weight, _doc in LEGAL_RELATIONS.values()
}

POSTGRES_LEXICAL_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ỹĐđ]+", re.UNICODE)
POSTGRES_TEXT_SEARCH_EXPRESSION = (
    "to_tsvector('simple', coalesce(title, '') || ' ' || "
    "coalesce(citation, '') || ' ' || coalesce(text, ''))"
)
POSTGRES_LEXICAL_STOP_WORDS = {
    "theo", "quy", "định", "dinh", "cho", "tôi", "toi", "hỏi", "hoi",
    "như", "nhu", "nào", "nao", "về", "ve", "và", "va", "là", "la",
    "của", "cua", "được", "duoc", "không", "khong", "trong", "những",
    "nhung", "gì", "gi", "các", "cac", "một", "mot", "số", "so",
}
CURRENT_LAW_STATUSES = ("IN_FORCE", "PARTIALLY_IN_FORCE", "AMENDED")
SETTLED_LAW_STATUSES = (
    *CURRENT_LAW_STATUSES,
    "EXPIRED",
    "REPLACED",
    "UNKNOWN",
)
UNVERIFIED_LAW_STATUS = "UNVERIFIED"
DOCUMENT_STRUCTURE_COUNTS_RE = re.compile(
    r"STRUCTURE_COUNTS:\s*"
    r"chapters=(?P<chapters>\d+);\s*"
    r"sections=(?P<sections>\d+);\s*"
    r"articles=(?P<articles>\d+);\s*"
    r"clauses=(?P<clauses>\d+);\s*"
    r"points=(?P<points>\d+);\s*"
    r"first_article=(?P<first_article>[^;.\s]*);\s*"
    r"last_article=(?P<last_article>[^;.\s]*)(?:[.;]|$)",
    re.IGNORECASE,
)


def document_structure_counts(
    row: dict[str, Any],
) -> dict[str, int | str] | None:
    """Decode the machine-readable graph counts embedded in a structure chunk."""

    match = DOCUMENT_STRUCTURE_COUNTS_RE.search(str(row.get("text") or ""))
    if match is None:
        return None
    return {
        "chapters": int(match.group("chapters")),
        "sections": int(match.group("sections")),
        "articles": int(match.group("articles")),
        "clauses": int(match.group("clauses")),
        "points": int(match.group("points")),
        "first_article": match.group("first_article"),
        "last_article": match.group("last_article"),
    }


def merge_chunk_rows(
    preferred: dict[str, Any],
    supplement: dict[str, Any],
) -> dict[str, Any]:
    """Fill gaps from a graph row without dropping richer provenance."""
    merged = dict(supplement)
    for key, value in preferred.items():
        if value is not None and value != "":
            merged[key] = value
        else:
            merged.setdefault(key, value)
    return merged


def _normalized_law_code(value: Any) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()[:120]


def _positive_version(value: Any) -> int:
    try:
        version = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, version)


def _verified_provenance_flag(value: Any) -> bool:
    return value is True or (
        isinstance(value, str)
        and value.strip().lower() in {"true", "verified"}
    )


def _verified_https_source(value: Any) -> str | None:
    source_url = str(value or "").strip()
    try:
        parsed = urlparse(source_url)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or (port is not None and port != 443)
    ):
        return None
    return source_url


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid provenance JSONL at {path}:{line_number}"
                ) from exc
            if not isinstance(row, dict):
                raise ValueError(
                    f"Invalid provenance record at {path}:{line_number}"
                )
            records.append(row)
    return records


def load_bootstrap_document_metadata(
    db_path: Path | str,
) -> dict[str, dict[str, Any]]:
    """Load explicit provenance or quarantine legacy documents.

    A local filename/code is useful for discovery but is not proof of current
    legal effect. Only an explicit verified provenance record with an HTTPS
    source and a settled lifecycle status can become retrievable.
    """
    db_path = Path(db_path)
    records = {
        str(row.get("doc_id") or ""): dict(row)
        for row in sqlite_rows(db_path, "docs")
        if str(row.get("doc_id") or "")
    }
    for filename in ("documents.jsonl", "document_provenance.jsonl"):
        for row in _read_jsonl_records(db_path.parent / filename):
            doc_id = str(row.get("doc_id") or "")
            if not doc_id:
                continue
            records[doc_id] = {**records.get(doc_id, {}), **row}

    metadata: dict[str, dict[str, Any]] = {}
    for doc_id, row in records.items():
        nested = row.get("provenance")
        provenance = nested if isinstance(nested, dict) else {}
        code = _normalized_law_code(
            provenance.get("law_code")
            or provenance.get("code")
            or row.get("law_code")
            or row.get("code")
        )
        title = str(row.get("title") or provenance.get("title") or code).strip()
        status = str(
            provenance.get("law_status")
            or provenance.get("status")
            or row.get("law_status")
            or row.get("status")
            or ""
        ).strip().upper()
        source_url = _verified_https_source(
            provenance.get("source_url") or row.get("source_url")
        )
        verified = _verified_provenance_flag(
            provenance.get("provenance_verified")
            if "provenance_verified" in provenance
            else row.get("provenance_verified")
        )
        if not (
            verified
            and code
            and source_url
            and status in SETTLED_LAW_STATUSES
        ):
            status = UNVERIFIED_LAW_STATUS
            source_url = None
        metadata[doc_id] = {
            "doc_id": doc_id,
            "title": title,
            "law_code": code or None,
            "source_url": source_url,
            "law_status": status,
            "law_version": _positive_version(
                provenance.get("law_version")
                or provenance.get("version")
                or row.get("law_version")
                or row.get("version")
            ),
            "provenance_verified": status != UNVERIFIED_LAW_STATUS,
        }
    return metadata


def bootstrap_provenance(
    metadata: dict[str, dict[str, Any]],
    doc_id: Any,
) -> dict[str, Any]:
    """Return explicit lifecycle fields for every bootstrap graph row."""

    row = metadata.get(str(doc_id or ""))
    if row is not None:
        return {
            "law_code": row["law_code"],
            "source_url": row["source_url"],
            "law_status": row["law_status"],
            "law_version": row["law_version"],
            "provenance_verified": row["provenance_verified"],
        }
    return {
        "law_code": None,
        "source_url": None,
        "law_status": UNVERIFIED_LAW_STATUS,
        "law_version": 1,
        "provenance_verified": False,
    }


def postgres_latest_chunk_predicate(alias: str) -> str:
    """SQL predicate that admits the latest indexed version of each law."""
    normalized_code = f"""
        upper(
            regexp_replace(
                btrim({alias}.law_code),
                '[[:space:]]+',
                '',
                'g'
            )
        )
    """
    return f"""
        {alias}.law_code IS NOT NULL
        AND {alias}.law_version IS NOT NULL
        AND EXISTS (
            SELECT 1
            FROM graphrag_law_version AS latest_law
            WHERE latest_law.law_code_normalized = {normalized_code}
              AND latest_law.latest_version = {alias}.law_version
        )
    """


def postgres_current_chunk_predicate(alias: str) -> str:
    """SQL predicate for the latest indexed version with a current status."""
    statuses = ", ".join(f"'{status}'" for status in CURRENT_LAW_STATUSES)
    return f"""
        {postgres_latest_chunk_predicate(alias)}
        AND {alias}.law_status IN ({statuses})
    """


@dataclass(frozen=True)
class ExternalGraphRAGConfig:
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    database_url: str = "postgresql+asyncpg://vlegal:vlegal@localhost:5432/vlegal"
    postgres_vector_size: int = 1024
    batch_size: int = 256
    embedding_provider: str = "vertex"
    embedding_model: str = "gemini-embedding-001"
    embedding_project_id: str = ""
    embedding_location: str = "global"
    embedding_credentials_path: str = "env.json"
    embedding_use_adc: bool = False
    embedding_api_key: str = field(default="", repr=False)
    embedding_max_concurrency: int = 8
    embedding_batch_size: int = 20
    embedding_timeout_seconds: float = 60.0
    embedding_max_retries: int = 3
    embedding_auto_truncate: bool = True
    embedding_data_policy: str = "redact"
    embedding_vertex_locations: tuple[str, ...] = ()
    embedding_vertex_requests_per_minute: float = 0.0
    hybrid_vector_weight: float = 0.55
    hybrid_bm25_weight: float = 0.45
    hybrid_rrf_k: int = 60
    bm25_k1: float = 1.5
    bm25_b: float = 0.75

    @classmethod
    def from_env(cls) -> "ExternalGraphRAGConfig":
        return cls(
            neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
            neo4j_password=os.getenv("NEO4J_PASSWORD", ""),
            neo4j_database=os.getenv("NEO4J_DATABASE", "neo4j"),
            database_url=os.getenv(
                "DATABASE_URL",
                "postgresql+asyncpg://vlegal:vlegal@localhost:5432/vlegal",
            ),
            postgres_vector_size=int(os.getenv("POSTGRES_VECTOR_SIZE", "1024")),
            batch_size=int(os.getenv("EXTERNAL_SYNC_BATCH_SIZE", "256")),
            embedding_provider=os.getenv("EMBEDDING_PROVIDER", "vertex"),
            embedding_model=os.getenv("EMBEDDING_MODEL", "gemini-embedding-001"),
            embedding_project_id=os.getenv("GEMINI_PROJECT_ID", ""),
            embedding_location=os.getenv(
                "EMBEDDING_LOCATION",
                "global",
            ),
            embedding_credentials_path=os.getenv(
                "GEMINI_CREDENTIALS_PATH",
                "env.json",
            ),
            embedding_use_adc=os.getenv("GEMINI_USE_ADC", "").strip().lower()
            in {"1", "true", "yes", "on"},
            embedding_api_key=os.getenv("GEMINI_API_KEY", ""),
            embedding_max_concurrency=int(
                os.getenv("EMBEDDING_MAX_CONCURRENCY", "8")
            ),
            embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "20")),
            embedding_timeout_seconds=float(
                os.getenv("EMBEDDING_TIMEOUT_SECONDS", "60")
            ),
            embedding_max_retries=int(os.getenv("EMBEDDING_MAX_RETRIES", "3")),
            embedding_auto_truncate=os.getenv(
                "EMBEDDING_AUTO_TRUNCATE",
                "true",
            ).strip().lower()
            in {"1", "true", "yes", "on"},
            embedding_data_policy=os.getenv(
                "GEMINI_DATA_POLICY",
                "redact",
            ).strip().lower(),
            embedding_vertex_locations=parse_vertex_locations(
                os.getenv("EMBEDDING_VERTEX_LOCATIONS", "")
            ),
            embedding_vertex_requests_per_minute=float(
                os.getenv("EMBEDDING_VERTEX_REQUESTS_PER_MINUTE", "0")
            ),
            hybrid_vector_weight=float(os.getenv("HYBRID_VECTOR_WEIGHT", "0.55")),
            hybrid_bm25_weight=float(os.getenv("HYBRID_BM25_WEIGHT", "0.45")),
            hybrid_rrf_k=int(os.getenv("HYBRID_RRF_K", "60")),
            bm25_k1=float(os.getenv("BM25_K1", "1.5")),
            bm25_b=float(os.getenv("BM25_B", "0.75")),
        )

    @property
    def embedding_config(self) -> EmbeddingConfig:
        return EmbeddingConfig(
            provider=self.embedding_provider,
            model=self.embedding_model,
            project_id=self.embedding_project_id,
            location=self.embedding_location,
            credentials_path=self.embedding_credentials_path,
            use_adc=self.embedding_use_adc,
            api_key=self.embedding_api_key,
            dimensions=self.postgres_vector_size,
            max_concurrency=self.embedding_max_concurrency,
            batch_size=self.embedding_batch_size,
            timeout_seconds=self.embedding_timeout_seconds,
            max_retries=self.embedding_max_retries,
            auto_truncate=self.embedding_auto_truncate,
            data_policy=self.embedding_data_policy,
            vertex_locations=self.embedding_vertex_locations,
            vertex_requests_per_minute=(
                self.embedding_vertex_requests_per_minute
            ),
        )

    @property
    def ready(self) -> bool:
        return bool(self.neo4j_password and self.database_url)

    @property
    def neo4j_ready(self) -> bool:
        return bool(self.neo4j_password)

    @property
    def postgres_ready(self) -> bool:
        return bool(self.database_url)


def relation_type(relation: str) -> str:
    key = strip_accents(relation).upper()
    return RELATION_TYPE_MAP.get(key, "RELATED_TO")


def batched(rows: Iterable[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    batch: list[dict[str, Any]] = []
    for row in rows:
        batch.append(row)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def sqlite_rows(db_path: Path | str, table: str) -> list[dict[str, Any]]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(row) for row in conn.execute(f"SELECT * FROM {table}")]
    finally:
        conn.close()


def validate_sqlite_embedding_metadata(db_path: Path | str, config: ExternalGraphRAGConfig) -> None:
    try:
        rows = sqlite_rows(db_path, "index_metadata")
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            "SQLite GraphRAG has no trusted embedding metadata; rebuild the index."
        ) from exc
    metadata = {str(row["key"]): str(row["value"]) for row in rows}
    expected = {
        "embedding_model": config.embedding_model,
        "embedding_revision": config.embedding_config.model_revision,
        "embedding_dimensions": str(config.postgres_vector_size),
    }
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise RuntimeError(
            f"SQLite GraphRAG embeddings {metadata!r} do not match "
            f"{expected!r}; rebuild the index before syncing."
        )


def postgres_dsn(database_url: str) -> str:
    """Convert SQLAlchemy async URLs to a DSN accepted by psycopg."""
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise ValueError("DATABASE_URL must point to PostgreSQL")
    query = dict(url.query)
    if "ssl" in query and "sslmode" not in query:
        query["sslmode"] = query.pop("ssl")
    return url.set(drivername="postgresql", query=query).render_as_string(hide_password=False)


def postgres_connection(config: ExternalGraphRAGConfig):
    return psycopg.connect(
        postgres_dsn(config.database_url),
        row_factory=dict_row,
        autocommit=True,
    )


def neo4j_driver(config: ExternalGraphRAGConfig):
    return GraphDatabase.driver(
        config.neo4j_uri,
        auth=(config.neo4j_user, config.neo4j_password),
    )


def ensure_neo4j_schema(driver, database: str) -> None:
    statements = [
        "CREATE CONSTRAINT legal_node_id IF NOT EXISTS FOR (n:LegalNode) REQUIRE n.node_id IS UNIQUE",
        "CREATE CONSTRAINT legal_chunk_id IF NOT EXISTS FOR (c:LegalChunk) REQUIRE c.chunk_id IS UNIQUE",
        "CREATE INDEX legal_node_type IF NOT EXISTS FOR (n:LegalNode) ON (n.node_type)",
        "CREATE INDEX legal_node_doc IF NOT EXISTS FOR (n:LegalNode) ON (n.doc_id)",
        "CREATE INDEX legal_document_code IF NOT EXISTS FOR (n:LegalDocument) ON (n.code)",
        "CREATE INDEX legal_article_number IF NOT EXISTS FOR (n:LegalArticle) ON (n.number)",
        "CREATE INDEX legal_chunk_node IF NOT EXISTS FOR (c:LegalChunk) ON (c.node_id)",
        "CREATE INDEX legal_chunk_type IF NOT EXISTS FOR (c:LegalChunk) ON (c.chunk_type)",
        "CREATE FULLTEXT INDEX legal_chunk_fulltext IF NOT EXISTS FOR (c:LegalChunk) ON EACH [c.title, c.citation, c.text]",
    ]
    with driver.session(database=database) as session:
        for statement in statements:
            session.run(statement)


def sync_neo4j(
    db_path: Path | str = DEFAULT_DB_PATH,
    config: ExternalGraphRAGConfig | None = None,
    reset: bool = False,
) -> dict[str, int]:
    config = config or ExternalGraphRAGConfig.from_env()
    if not config.neo4j_password:
        raise RuntimeError("NEO4J_PASSWORD is required to sync Neo4j.")

    nodes = sqlite_rows(db_path, "nodes")
    edges = sqlite_rows(db_path, "edges")
    validate_sqlite_embedding_metadata(db_path, config)
    chunks = sqlite_rows(db_path, "chunks")
    document_metadata = load_bootstrap_document_metadata(db_path)

    driver = neo4j_driver(config)
    try:
        ensure_neo4j_schema(driver, config.neo4j_database)
        with driver.session(database=config.neo4j_database) as session:
            if reset:
                session.run("MATCH (c:LegalChunk) DETACH DELETE c")
                session.run("MATCH (n:LegalNode) DETACH DELETE n")

            for batch in batched(nodes, config.batch_size):
                prepared = []
                for source in batch:
                    row = dict(source)
                    provenance = bootstrap_provenance(
                        document_metadata,
                        row.get("doc_id"),
                    )
                    row.update(provenance)
                    prepared.append(row)
                session.run(
                    """
                    UNWIND $rows AS row
                    MERGE (n:LegalNode {node_id: row.node_id})
                    SET n.doc_id = row.doc_id,
                        n.node_type = row.node_type,
                        n.label = row.label,
                        n.number = row.number,
                        n.title = row.title,
                        n.parent_id = row.parent_id,
                        n.path_label = row.path_label,
                        n.text = row.text,
                        n.ordinal = row.ordinal,
                        n.direct_child_count = row.direct_child_count,
                        n.chapter_count = row.chapter_count,
                        n.section_count = row.section_count,
                        n.article_count = row.article_count,
                        n.clause_count = row.clause_count,
                        n.point_count = row.point_count,
                        n.first_article_number = row.first_article_number,
                        n.last_article_number = row.last_article_number,
                        n.code = row.law_code,
                        n.status = row.law_status,
                        n.version = row.law_version,
                        n.law_code = row.law_code,
                        n.law_status = row.law_status,
                        n.law_version = row.law_version,
                        n.source_url = row.source_url,
                        n.provenance_verified = row.provenance_verified
                    """,
                    rows=prepared,
                )

            session.run(
                """
                MATCH (n:LegalNode)
                WHERE n.node_type IN ['VănBản', 'document']
                SET n:LegalDocument
                """
            )
            session.run(
                """
                MATCH (n:LegalNode)
                WHERE n.node_type = 'Điều'
                SET n:LegalArticle
                """
            )
            session.run(
                """
                MATCH (n:LegalNode)
                WHERE n.node_type = 'Khoản'
                SET n:LegalClause
                """
            )
            session.run(
                """
                MATCH (n:LegalNode)
                WHERE n.node_type = 'Điểm'
                SET n:LegalPoint
                """
            )

            for batch in batched(chunks, config.batch_size):
                prepared = []
                for source in batch:
                    row = dict(source)
                    row.pop("vector", None)
                    provenance = bootstrap_provenance(
                        document_metadata,
                        row.get("doc_id"),
                    )
                    row.update(provenance)
                    prepared.append(row)
                session.run(
                    """
                    UNWIND $rows AS row
                    MERGE (c:LegalChunk {chunk_id: row.chunk_id})
                    SET c.doc_id = row.doc_id,
                        c.node_id = row.node_id,
                        c.chunk_type = row.chunk_type,
                        c.title = row.title,
                        c.path_label = row.path_label,
                        c.citation = row.citation,
                        c.text = row.text,
                        c.token_count = row.token_count,
                        c.ordinal = row.ordinal,
                        c.law_code = row.law_code,
                        c.law_status = row.law_status,
                        c.law_version = row.law_version,
                        c.source_url = row.source_url,
                        c.provenance_verified = row.provenance_verified
                    WITH c, row
                    MATCH (n:LegalNode {node_id: row.node_id})
                    MERGE (c)-[:CHUNK_OF]->(n)
                    """,
                    rows=prepared,
                )

            grouped: dict[str, list[dict[str, Any]]] = {}
            for edge in edges:
                grouped.setdefault(relation_type(edge["relation"]), []).append(edge)

            for rel_type, rel_edges in grouped.items():
                for batch in batched(rel_edges, config.batch_size):
                    session.run(
                        f"""
                        UNWIND $rows AS row
                        MATCH (s:LegalNode {{node_id: row.source_id}})
                        MATCH (t:LegalNode {{node_id: row.target_id}})
                        MERGE (s)-[r:{rel_type} {{edge_id: row.edge_id}}]->(t)
                        SET r.relation = row.relation,
                            r.evidence = row.evidence
                        """,
                        rows=batch,
                    )
    finally:
        driver.close()

    return {"nodes": len(nodes), "edges": len(edges), "chunks": len(chunks)}


def vector_literal(values: Iterable[float]) -> str:
    return "[" + ",".join(f"{float(value):.8g}" for value in values) + "]"


def postgres_dense_vector(
    text: str,
    config: ExternalGraphRAGConfig,
) -> list[float] | None:
    try:
        return get_embedding_service(config.embedding_config).embed_query(text)
    except Exception as exc:
        logger.warning(
            "Vertex AI embedding unavailable; skipping dense retrieval and "
            "continuing with lexical retrieval: %s",
            exc,
        )
        return None


def ensure_postgres_schema(config: ExternalGraphRAGConfig, reset: bool = False) -> None:
    if config.postgres_vector_size != 1024:
        raise ValueError(
            "POSTGRES_VECTOR_SIZE must be 1024 for the current pgvector schema."
        )
    with postgres_connection(config) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS graphrag_chunk (
                    chunk_id VARCHAR(255) PRIMARY KEY,
                    doc_id VARCHAR(255) NOT NULL,
                    node_id VARCHAR(255) NOT NULL,
                    chunk_type VARCHAR(32) NOT NULL,
                    title TEXT NOT NULL DEFAULT '',
                    path_label TEXT NOT NULL DEFAULT '',
                    citation TEXT NOT NULL DEFAULT '',
                    text TEXT NOT NULL,
                    token_count INTEGER NOT NULL DEFAULT 0,
                    ordinal INTEGER NOT NULL DEFAULT 0,
                    source_url TEXT,
                    law_code VARCHAR(120),
                    law_status VARCHAR(32),
                    law_version INTEGER,
                    embedding_model VARCHAR(255) NOT NULL,
                    embedding_revision VARCHAR(255) NOT NULL,
                    embedding vector({config.postgres_vector_size}) NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute(
                """
                SELECT atttypmod AS dimensions
                FROM pg_attribute
                WHERE attrelid = 'graphrag_chunk'::regclass
                  AND attname = 'embedding'
                  AND NOT attisdropped
                """
            )
            vector_row = cursor.fetchone()
            actual_dimensions = int(vector_row["dimensions"]) if vector_row else 0
            if actual_dimensions != config.postgres_vector_size:
                raise RuntimeError(
                    f"graphrag_chunk.embedding is vector({actual_dimensions}), expected "
                    f"vector({config.postgres_vector_size}); run Alembic migration 20260721_0003."
                )
            cursor.execute(
                "ALTER TABLE graphrag_chunk ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(255)"
            )
            cursor.execute(
                "ALTER TABLE graphrag_chunk ADD COLUMN IF NOT EXISTS embedding_revision VARCHAR(255)"
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS graphrag_law_version (
                    law_code_normalized VARCHAR(120) PRIMARY KEY,
                    latest_version INTEGER NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute(
                """
                INSERT INTO graphrag_law_version (
                    law_code_normalized,
                    latest_version,
                    updated_at
                )
                SELECT
                    upper(
                        regexp_replace(
                            btrim(law_code),
                            '[[:space:]]+',
                            '',
                            'g'
                        )
                    ),
                    max(law_version),
                    now()
                FROM graphrag_chunk
                WHERE law_code IS NOT NULL AND law_version IS NOT NULL
                GROUP BY 1
                ON CONFLICT (law_code_normalized) DO UPDATE SET
                    latest_version = GREATEST(
                        graphrag_law_version.latest_version,
                        EXCLUDED.latest_version
                    ),
                    updated_at = now()
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_graphrag_chunk_doc_id ON graphrag_chunk (doc_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_graphrag_chunk_node_id ON graphrag_chunk (node_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_graphrag_chunk_type ON graphrag_chunk (chunk_type)")
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_graphrag_chunk_law_code_version
                ON graphrag_chunk (
                    upper(
                        regexp_replace(
                            btrim(law_code),
                            '[[:space:]]+',
                            '',
                            'g'
                        )
                    ),
                    law_version DESC
                )
                WHERE law_code IS NOT NULL AND law_version IS NOT NULL
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_graphrag_chunk_search ON graphrag_chunk USING gin (
                    to_tsvector('simple', coalesce(title, '') || ' ' || coalesce(citation, '') || ' ' || coalesce(text, ''))
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS ix_graphrag_chunk_embedding_hnsw
                ON graphrag_chunk USING hnsw (embedding vector_cosine_ops)
                WITH (m = 16, ef_construction = 64)
                """
            )
            if reset:
                cursor.execute(
                    "TRUNCATE TABLE graphrag_chunk, graphrag_law_version"
                )


def drop_postgres_bulk_load_indexes(config: ExternalGraphRAGConfig) -> None:
    """Drop rebuildable indexes before a full corpus reload."""

    with postgres_connection(config) as connection:
        with connection.cursor() as cursor:
            cursor.execute("DROP INDEX IF EXISTS ix_graphrag_chunk_search")
            cursor.execute(
                "DROP INDEX IF EXISTS ix_graphrag_chunk_embedding_hnsw"
            )


def validate_postgres_embeddings(connection, config: ExternalGraphRAGConfig) -> None:
    metadata_row: dict[str, Any] | None = None
    with connection.cursor() as cursor:
        try:
            cursor.execute(
                """
                SELECT embedding_model, embedding_revision,
                       embedding_dimensions AS dimensions, status
                FROM graphrag_index_metadata
                WHERE index_name = 'active'
                """
            )
            metadata_row = cursor.fetchone()
        except psycopg.errors.UndefinedTable:
            # Compatibility for a database that has not run migration 0015.
            # Production uses the constant-time metadata lookup above.
            metadata_row = None

        if metadata_row is None:
            cursor.execute(
                """
                SELECT embedding_model, embedding_revision,
                       vector_dims(embedding) AS dimensions
                FROM graphrag_chunk
                GROUP BY embedding_model, embedding_revision,
                         vector_dims(embedding)
                ORDER BY embedding_model, embedding_revision, dimensions
                LIMIT 2
                """
            )
            rows = cursor.fetchall()
            if not rows:
                return
            actual = {
                (
                    row["embedding_model"],
                    row["embedding_revision"],
                    int(row["dimensions"]),
                )
                for row in rows
            }
        else:
            if str(metadata_row.get("status") or "").lower() != "ready":
                raise RuntimeError(
                    "PostgreSQL GraphRAG index is not ready; retry after indexing completes."
                )
            actual = {
                (
                    metadata_row["embedding_model"],
                    metadata_row["embedding_revision"],
                    int(metadata_row["dimensions"]),
                )
            }
    expected = (
        config.embedding_model,
        config.embedding_config.model_revision,
        config.postgres_vector_size,
    )
    if actual != {expected}:
        raise RuntimeError(
            f"PostgreSQL embeddings {actual!r} do not match configured model {expected!r}; re-embed the corpus."
        )


def update_postgres_index_metadata(
    config: ExternalGraphRAGConfig,
    chunk_count: int,
) -> None:
    """Publish the completed vector contract for constant-time startup checks."""

    try:
        with postgres_connection(config) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO graphrag_index_metadata (
                        index_name, embedding_provider, embedding_model,
                        embedding_revision, embedding_dimensions, status,
                        chunk_count, updated_at
                    )
                    VALUES (
                        'active', %s, %s, %s, %s, 'ready', %s, now()
                    )
                    ON CONFLICT (index_name) DO UPDATE SET
                        embedding_provider = EXCLUDED.embedding_provider,
                        embedding_model = EXCLUDED.embedding_model,
                        embedding_revision = EXCLUDED.embedding_revision,
                        embedding_dimensions = EXCLUDED.embedding_dimensions,
                        status = EXCLUDED.status,
                        chunk_count = EXCLUDED.chunk_count,
                        updated_at = now()
                    """,
                    (
                        config.embedding_provider,
                        config.embedding_model,
                        config.embedding_config.model_revision,
                        config.postgres_vector_size,
                        max(0, int(chunk_count)),
                    ),
                )
    except psycopg.errors.UndefinedTable:
        logger.warning(
            "graphrag_index_metadata is unavailable; run Alembic migration 0015."
        )


def upsert_postgres_chunks(
    rows: Iterable[dict[str, Any]],
    config: ExternalGraphRAGConfig,
) -> int:
    sources = [dict(source) for source in rows]
    if not sources:
        return 0

    prepared: list[dict[str, Any]] = []
    missing_indices: list[int] = []
    missing_texts: list[str] = []
    for source in sources:
        row = dict(source)
        vector_text = f"{row.get('title', '')}\n{row.get('path_label', '')}\n{row.get('text', '')}"
        stored_vector = row.pop("vector", None)
        if stored_vector is None:
            missing_indices.append(len(prepared))
            missing_texts.append(vector_text)
            row["embedding"] = vector_literal([0.0] * config.postgres_vector_size)
        else:
            values = list(blob_to_vector(bytes(stored_vector)))
            if len(values) != config.postgres_vector_size:
                missing_indices.append(len(prepared))
                missing_texts.append(vector_text)
                values = [0.0] * config.postgres_vector_size
            row["embedding"] = vector_literal(values)
        row["embedding_model"] = config.embedding_model
        row["embedding_revision"] = config.embedding_config.model_revision
        prepared.append(row)

    if missing_texts:
        service = get_embedding_service(config.embedding_config)
        embeddings = service.embed_documents(missing_texts)
        for index, values in zip(missing_indices, embeddings, strict=True):
            prepared[index]["embedding"] = vector_literal(values)

    statement = """
        INSERT INTO graphrag_chunk (
            chunk_id, doc_id, node_id, chunk_type, title, path_label, citation,
            text, token_count, ordinal, source_url, law_code, law_status,
            law_version, embedding_model, embedding_revision, embedding, updated_at
        ) VALUES (
            %(chunk_id)s, %(doc_id)s, %(node_id)s, %(chunk_type)s,
            %(title)s, %(path_label)s, %(citation)s, %(text)s,
            %(token_count)s, %(ordinal)s, %(source_url)s, %(law_code)s,
            %(law_status)s, %(law_version)s, %(embedding_model)s,
            %(embedding_revision)s, %(embedding)s::vector, now()
        )
        ON CONFLICT (chunk_id) DO UPDATE SET
            doc_id = EXCLUDED.doc_id,
            node_id = EXCLUDED.node_id,
            chunk_type = EXCLUDED.chunk_type,
            title = EXCLUDED.title,
            path_label = EXCLUDED.path_label,
            citation = EXCLUDED.citation,
            text = EXCLUDED.text,
            token_count = EXCLUDED.token_count,
            ordinal = EXCLUDED.ordinal,
            source_url = EXCLUDED.source_url,
            law_code = EXCLUDED.law_code,
            law_status = EXCLUDED.law_status,
            law_version = EXCLUDED.law_version,
            embedding_model = EXCLUDED.embedding_model,
            embedding_revision = EXCLUDED.embedding_revision,
            embedding = EXCLUDED.embedding,
            updated_at = now()
    """
    with postgres_connection(config) as connection:
        # `postgres_connection` is autocommit for read-heavy runtime paths.
        # Use an explicit transaction here so a failed batch cannot expose
        # only a prefix of a new legal-document version.
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.executemany(statement, prepared)
                latest_versions: dict[str, int] = {}
                for row in prepared:
                    normalized_code = _normalized_law_code(row.get("law_code"))
                    if not normalized_code:
                        continue
                    latest_versions[normalized_code] = max(
                        latest_versions.get(normalized_code, 0),
                        _positive_version(row.get("law_version")),
                    )
                if latest_versions:
                    cursor.executemany(
                        """
                        INSERT INTO graphrag_law_version (
                            law_code_normalized,
                            latest_version,
                            updated_at
                        )
                        VALUES (
                            %(law_code_normalized)s,
                            %(latest_version)s,
                            now()
                        )
                        ON CONFLICT (law_code_normalized) DO UPDATE SET
                            latest_version = GREATEST(
                                graphrag_law_version.latest_version,
                                EXCLUDED.latest_version
                            ),
                            updated_at = now()
                        """,
                        [
                            {
                                "law_code_normalized": code,
                                "latest_version": version,
                            }
                            for code, version in latest_versions.items()
                        ],
                    )
    return len(prepared)


def score_chunk_payload(
    row: dict[str, Any],
    query: str,
    base_score: float,
    rank: int,
) -> float:
    query_ascii = strip_accents(query).lower()
    terms = key_terms(query)
    haystack = strip_accents(
        f"{row.get('title', '')} {row.get('citation', '')} {row.get('text', '')[:700]}"
    ).lower()
    score = float(base_score) * (1.0 / max(1.0, rank**0.35))
    if terms:
        matched = sum(1 for term in terms if term in haystack)
        score += (matched / min(len(terms), 10)) * 0.9
    if "duoc" in query_ascii and "khong duoc" not in query_ascii and "khong duoc" in haystack:
        score -= 0.35
    if "khong duoc" in query_ascii and "khong duoc" in haystack:
        score += 0.5
    if (
        "nguoi su dung lao dong" in query_ascii
        and "don phuong" in query_ascii
        and "cham dut" in query_ascii
        and "quyen don phuong cham dut hop dong lao dong cua nguoi su dung lao dong" in haystack
    ):
        score += 1.15
    if row.get("chunk_type") in {"article", "clause", "point"}:
        score += 0.08
    return score


def postgres_lexical_terms(query: str, limit: int = 18) -> list[str]:
    """Return PostgreSQL `simple` dictionary terms while retaining Vietnamese accents."""
    terms: list[str] = []
    for token in POSTGRES_LEXICAL_TOKEN_RE.findall(query.lower()):
        if len(token) < 2 and not token.isdigit():
            continue
        if token in POSTGRES_LEXICAL_STOP_WORDS or strip_accents(token) in POSTGRES_LEXICAL_STOP_WORDS:
            continue
        terms.append(token)
    return list(dict.fromkeys(terms))[:limit]


def postgres_or_tsquery(terms: Iterable[str]) -> str:
    """Build a safe OR tsquery from terms already restricted by the lexical regex."""
    return " | ".join(f"'{term.replace(chr(39), chr(39) * 2)}'" for term in terms)


def bm25_score(
    row: dict[str, Any],
    terms: Iterable[str],
    document_frequencies: dict[str, int],
    total_documents: int,
    average_document_length: float,
    *,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    """Compute Okapi BM25 over the same title/citation/text fields as the GIN index."""
    if total_documents <= 0:
        return 0.0
    text = f"{row.get('title', '')} {row.get('citation', '')} {row.get('text', '')}".lower()
    frequencies = Counter(POSTGRES_LEXICAL_TOKEN_RE.findall(text))
    document_length = max(int(row.get("token_count") or 0), 1)
    average_length = max(float(average_document_length), 1.0)
    score = 0.0
    for term in dict.fromkeys(terms):
        term_frequency = frequencies.get(term, 0)
        if term_frequency <= 0:
            continue
        document_frequency = min(max(int(document_frequencies.get(term, 0)), 0), total_documents)
        inverse_document_frequency = math.log1p(
            (total_documents - document_frequency + 0.5) / (document_frequency + 0.5)
        )
        denominator = term_frequency + k1 * (
            1.0 - b + b * document_length / average_length
        )
        score += inverse_document_frequency * (
            term_frequency * (k1 + 1.0) / max(denominator, 1e-9)
        )
    return score


def reciprocal_rank_fusion(
    rankings: Iterable[tuple[Iterable[str], float]],
    rank_constant: int = 60,
) -> dict[str, float]:
    """Fuse independent rankings with weighted Reciprocal Rank Fusion."""
    k = max(int(rank_constant), 1)
    scores: dict[str, float] = {}
    for identifiers, weight in rankings:
        for rank, identifier in enumerate(dict.fromkeys(identifiers), start=1):
            scores[identifier] = scores.get(identifier, 0.0) + float(weight) * (k + 1) / (k + rank)
    return scores


def lucene_escape(term: str) -> str:
    return re.sub(r'([+\-&|!(){}\[\]^"~*?:\\/])', r"\\\1", term)


def neo4j_fulltext_query(query: str) -> str:
    stop = {"theo", "quy", "dinh", "cho", "toi", "hoi", "nhu", "nao", "ve", "va", "la", "cua", "duoc", "khong", "trong", "nhung", "gi", "cac", "mot", "so"}
    raw_terms = re.findall(r"\w+", query, flags=re.UNICODE)
    terms: list[str] = []
    for term in raw_terms:
        clean = term.strip()
        if len(clean) < 2:
            continue
        if strip_accents(clean).lower() in stop:
            continue
        terms.append(clean)
        ascii_term = strip_accents(clean)
        if ascii_term.lower() != clean.lower():
            terms.append(ascii_term)
    terms = list(dict.fromkeys(terms))[:16]
    if not terms:
        terms = raw_terms[:8] or [query]
    return " OR ".join(lucene_escape(term) for term in terms if term)


def sync_postgres(
    db_path: Path | str = DEFAULT_DB_PATH,
    config: ExternalGraphRAGConfig | None = None,
    reset: bool = False,
) -> dict[str, int]:
    config = config or ExternalGraphRAGConfig.from_env()
    if not config.postgres_ready:
        raise RuntimeError("DATABASE_URL is required to sync PostgreSQL.")

    validate_sqlite_embedding_metadata(db_path, config)
    chunks = sqlite_rows(db_path, "chunks")
    document_metadata = load_bootstrap_document_metadata(db_path)
    ensure_postgres_schema(config, reset=reset)
    if reset:
        drop_postgres_bulk_load_indexes(config)

    total = 0
    try:
        for batch in batched(chunks, config.batch_size):
            rows = []
            for row in batch:
                provenance = bootstrap_provenance(
                    document_metadata,
                    row.get("doc_id"),
                )
                rows.append({
                    "chunk_id": row["chunk_id"],
                    "doc_id": row["doc_id"],
                    "node_id": row["node_id"],
                    "chunk_type": row["chunk_type"],
                    "title": row["title"],
                    "path_label": row["path_label"],
                    "citation": row["citation"],
                    "text": row["text"],
                    "token_count": row["token_count"],
                    "ordinal": row["ordinal"],
                    "source_url": provenance["source_url"],
                    "law_code": provenance["law_code"],
                    "law_status": provenance["law_status"],
                    "law_version": provenance["law_version"],
                    "vector": row["vector"],
                })
            total += upsert_postgres_chunks(rows, config)
    finally:
        if reset:
            ensure_postgres_schema(config)

    update_postgres_index_metadata(config, total)
    return {"chunks": total}


def sync_external_graphrag(
    db_path: Path | str = DEFAULT_DB_PATH,
    config: ExternalGraphRAGConfig | None = None,
    reset_neo4j: bool = False,
    reset_postgres: bool = False,
    include_neo4j: bool = True,
    include_postgres: bool = True,
) -> dict[str, Any]:
    config = config or ExternalGraphRAGConfig.from_env()
    res = {}
    if include_neo4j:
        try:
            res["neo4j"] = sync_neo4j(db_path, config, reset=reset_neo4j)
        except Exception as exc:
            res["neo4j"] = {"error": f"{type(exc).__name__}: {exc}"}
    if include_postgres:
        try:
            res["postgres"] = sync_postgres(db_path, config, reset=reset_postgres)
        except Exception as exc:
            res["postgres"] = {"error": f"{type(exc).__name__}: {exc}"}
    return res


class PostgresGraphRAGStore:
    def __init__(self, config: ExternalGraphRAGConfig | None = None):
        self.config = config or ExternalGraphRAGConfig.from_env()
        if not self.config.postgres_ready:
            raise RuntimeError("PostgreSQL backend requires DATABASE_URL.")
        self.connection = postgres_connection(self.config)
        self._bm25_corpus_statistics: tuple[int, float] | None = None
        self._is_ready = True
        try:
            with self.connection.cursor() as cursor:
                cursor.execute("SELECT 1 FROM graphrag_chunk LIMIT 1")
            validate_postgres_embeddings(self.connection, self.config)
        except Exception as exc:
            logger.warning("PostgresGraphRAGStore chunk table or embeddings unavailable: %s", exc)
            self._is_ready = False

    def close(self) -> None:
        self.connection.close()

    def stats(self) -> dict[str, Any]:
        current_chunk = postgres_latest_chunk_predicate("current_chunk")
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT count(*) AS chunks,
                       count(
                           DISTINCT upper(
                               regexp_replace(
                                   btrim(current_chunk.law_code),
                                   '[[:space:]]+',
                                   '',
                                   'g'
                               )
                           )
                       ) AS documents
                FROM graphrag_chunk AS current_chunk
                WHERE {current_chunk}
                """
            )
            counts = cursor.fetchone() or {"chunks": 0, "documents": 0}
        return {
            "backend": "postgres_hybrid",
            "documents": counts["documents"],
            "nodes": 0,
            "edges": 0,
            "chunks": counts["chunks"],
            "relations": {},
            "retrieval": {"dense": "cosine", "lexical": "bm25", "fusion": "rrf"},
        }

    def document_structures(self, limit: int = 500) -> list[dict[str, Any]]:
        """Return one precomputed hierarchy summary for each latest law."""

        current_chunk = postgres_latest_chunk_predicate("current_chunk")
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT current_chunk.chunk_id, current_chunk.doc_id,
                       current_chunk.node_id, current_chunk.chunk_type,
                       current_chunk.title, current_chunk.path_label,
                       current_chunk.citation, current_chunk.text,
                       current_chunk.token_count, current_chunk.ordinal,
                       coalesce(
                           current_chunk.source_url,
                           official_document.source_url
                       ) AS source_url,
                       current_chunk.law_code,
                       current_chunk.law_status, current_chunk.law_version
                FROM graphrag_chunk AS current_chunk
                LEFT JOIN LATERAL (
                    SELECT document.source_url
                    FROM legal_document AS document
                    WHERE upper(
                              regexp_replace(
                                  btrim(document.code),
                                  '[[:space:]]+',
                                  '',
                                  'g'
                              )
                          ) = upper(
                              regexp_replace(
                                  btrim(current_chunk.law_code),
                                  '[[:space:]]+',
                                  '',
                                  'g'
                              )
                          )
                      AND document.source_url IS NOT NULL
                      AND btrim(document.source_url) <> ''
                    ORDER BY document.version DESC,
                             document.verified_at DESC NULLS LAST
                    LIMIT 1
                ) AS official_document ON TRUE
                WHERE {current_chunk}
                  AND current_chunk.chunk_type = 'document_structure'
                ORDER BY current_chunk.law_code, current_chunk.doc_id
                LIMIT %s
                """,
                (max(1, int(limit)),),
            )
            return [dict(row) for row in cursor.fetchall()]

    def retrieve(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        if not getattr(self, "_is_ready", True):
            return []
        query = normalize_space(query)
        if not query:
            return []
        candidate_limit = max(64, top_k * 8)
        vector_candidates = self._vector_candidates(query, candidate_limit)
        bm25_candidates = self._bm25_candidates(query, candidate_limit)
        if not vector_candidates and not bm25_candidates:
            return []

        vector_weight = max(float(self.config.hybrid_vector_weight), 0.0)
        bm25_weight = max(float(self.config.hybrid_bm25_weight), 0.0)
        total_weight = vector_weight + bm25_weight
        if total_weight <= 0:
            vector_weight = bm25_weight = 0.5
        else:
            vector_weight /= total_weight
            bm25_weight /= total_weight

        vector_ids = [row["chunk_id"] for row in vector_candidates]
        bm25_ids = [row["chunk_id"] for row in bm25_candidates]
        fused_scores = reciprocal_rank_fusion(
            [(vector_ids, vector_weight), (bm25_ids, bm25_weight)],
            self.config.hybrid_rrf_k,
        )
        rows_by_id = {row["chunk_id"]: dict(row) for row in vector_candidates}
        for row in bm25_candidates:
            rows_by_id.setdefault(row["chunk_id"], dict(row))
        vector_id_set = set(vector_ids)
        bm25_id_set = set(bm25_ids)

        rows = []
        ranked_ids = sorted(fused_scores, key=lambda chunk_id: (-fused_scores[chunk_id], chunk_id))
        for rank, chunk_id in enumerate(ranked_ids, start=1):
            row = rows_by_id[chunk_id]
            row.pop("_vector_score", None)
            row.pop("_bm25_score", None)
            row.pop("_fts_score", None)
            row["score"] = score_chunk_payload(row, query, fused_scores[chunk_id], rank)
            reasons = []
            if chunk_id in vector_id_set:
                reasons.append("postgres_vector_cosine")
            if chunk_id in bm25_id_set:
                reasons.append("postgres_bm25")
            row["reasons"] = reasons
            rows.append(row)

        rows.sort(key=lambda row: row["score"], reverse=True)
        selected = rows[:top_k]
        for idx, row in enumerate(selected, start=1):
            row["source_id"] = f"S{idx}"
            row["score"] = round(float(row["score"]), 4)
        return selected

    def _vector_candidates(self, query: str, limit: int) -> list[dict[str, Any]]:
        dense_vector = postgres_dense_vector(query, self.config)
        if dense_vector is None:
            return []
        query_vector = vector_literal(dense_vector)
        current_chunk = postgres_latest_chunk_predicate("current_chunk")
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT current_chunk.chunk_id, current_chunk.doc_id,
                       current_chunk.node_id, current_chunk.chunk_type,
                       current_chunk.title, current_chunk.path_label,
                       current_chunk.citation, current_chunk.text,
                       current_chunk.token_count, current_chunk.ordinal,
                       current_chunk.source_url, current_chunk.law_code,
                       current_chunk.law_status, current_chunk.law_version,
                       1 - (current_chunk.embedding <=> %s::vector) AS _vector_score
                FROM graphrag_chunk AS current_chunk
                WHERE {current_chunk}
                ORDER BY current_chunk.embedding <=> %s::vector
                LIMIT %s
                """,
                (query_vector, query_vector, limit),
            )
            return [dict(row) for row in cursor.fetchall()]

    def _bm25_candidates(self, query: str, limit: int) -> list[dict[str, Any]]:
        terms = postgres_lexical_terms(query)
        tsquery = postgres_or_tsquery(terms)
        if not tsquery:
            return []

        current_chunk = postgres_latest_chunk_predicate("current_chunk")
        frequency_chunk = postgres_latest_chunk_predicate("frequency_chunk")
        with self.connection.cursor() as cursor:
            cursor.execute(
                f"""
                WITH query AS (SELECT to_tsquery('simple', %s) AS value)
                SELECT current_chunk.chunk_id, current_chunk.doc_id,
                       current_chunk.node_id, current_chunk.chunk_type,
                       current_chunk.title, current_chunk.path_label,
                       current_chunk.citation, current_chunk.text,
                       current_chunk.token_count, current_chunk.ordinal,
                       current_chunk.source_url, current_chunk.law_code,
                       current_chunk.law_status, current_chunk.law_version,
                       ts_rank_cd({POSTGRES_TEXT_SEARCH_EXPRESSION}, query.value, 32) AS _fts_score
                FROM graphrag_chunk AS current_chunk
                CROSS JOIN query
                WHERE {current_chunk}
                  AND {POSTGRES_TEXT_SEARCH_EXPRESSION} @@ query.value
                ORDER BY _fts_score DESC, chunk_id
                LIMIT %s
                """,
                (tsquery, limit),
            )
            rows = [dict(row) for row in cursor.fetchall()]
            if not rows:
                return []
            cursor.execute(
                f"""
                SELECT term, (
                    SELECT count(*)
                    FROM graphrag_chunk AS frequency_chunk
                    WHERE {frequency_chunk}
                      AND {POSTGRES_TEXT_SEARCH_EXPRESSION} @@ plainto_tsquery('simple', term)
                ) AS document_frequency
                FROM unnest(%s::text[]) AS terms(term)
                """,
                (terms,),
            )
            document_frequencies = {
                str(row["term"]): int(row["document_frequency"])
                for row in cursor.fetchall()
            }

        total_documents, average_document_length = self._corpus_statistics()
        for row in rows:
            row["_bm25_score"] = bm25_score(
                row,
                terms,
                document_frequencies,
                total_documents,
                average_document_length,
                k1=self.config.bm25_k1,
                b=self.config.bm25_b,
            )
        rows.sort(key=lambda row: (-float(row["_bm25_score"]), row["chunk_id"]))
        return rows

    def _corpus_statistics(self) -> tuple[int, float]:
        if self._bm25_corpus_statistics is None:
            current_chunk = postgres_latest_chunk_predicate("current_chunk")
            with self.connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT count(*) AS documents,
                           coalesce(
                               avg(greatest(current_chunk.token_count, 1)),
                               1.0
                           ) AS average_length
                    FROM graphrag_chunk AS current_chunk
                    WHERE {current_chunk}
                    """
                )
                row = cursor.fetchone() or {"documents": 0, "average_length": 1.0}
            self._bm25_corpus_statistics = (
                int(row["documents"]),
                float(row["average_length"]),
            )
        return self._bm25_corpus_statistics


class Neo4jGraphRAGStore:
    def __init__(self, config: ExternalGraphRAGConfig | None = None):
        self.config = config or ExternalGraphRAGConfig.from_env()
        if not self.config.neo4j_ready:
            raise RuntimeError("Neo4j backend requires NEO4J_PASSWORD.")
        self.driver = neo4j_driver(self.config)
        self.driver.verify_connectivity()
        ensure_neo4j_schema(self.driver, self.config.neo4j_database)

    def close(self) -> None:
        self.driver.close()

    def stats(self) -> dict[str, Any]:
        with self.driver.session(database=self.config.neo4j_database) as session:
            row = session.run(
                """
                MATCH (d:LegalNode)
                WHERE d.node_id STARTS WITH 'doc:'
                WITH count(d) AS documents
                MATCH (n:LegalNode)
                WITH documents, count(n) AS nodes
                MATCH ()-[r]->()
                WHERE type(r) <> 'CHUNK_OF'
                WITH documents, nodes, count(r) AS edges
                MATCH (c:LegalChunk)
                RETURN documents, nodes, edges, count(c) AS chunks
                """
            ).single()
            rel_rows = session.run(
                """
                MATCH ()-[r]->()
                WHERE type(r) <> 'CHUNK_OF'
                RETURN type(r) AS relation, count(r) AS count
                ORDER BY count DESC
                """
            ).data()
            node_type_rows = session.run(
                """
                MATCH (n:LegalNode)
                RETURN n.node_type AS node_type, count(n) AS count
                ORDER BY count DESC
                """
            ).data()
        return {
            "backend": "neo4j",
            "documents": row["documents"] if row else 0,
            "nodes": row["nodes"] if row else 0,
            "edges": row["edges"] if row else 0,
            "chunks": row["chunks"] if row else 0,
            "relations": {item["relation"]: item["count"] for item in rel_rows},
            "node_types": {item["node_type"]: item["count"] for item in node_type_rows},
            "neo4j_uri": self.config.neo4j_uri,
        }

    def document_structures(self, limit: int = 500) -> list[dict[str, Any]]:
        with self.driver.session(database=self.config.neo4j_database) as session:
            return session.run(
                """
                MATCH (c:LegalChunk)-[:CHUNK_OF]->(document:LegalNode)
                WHERE c.chunk_type = 'document_structure'
                  AND coalesce(c.law_version, c.version) = document.version
                  AND NOT EXISTS {
                      MATCH (newer_document:LegalNode)
                      WHERE newer_document.node_type IN ['VănBản', 'document']
                        AND toUpper(replace(coalesce(newer_document.code, ''), ' ', ''))
                            = toUpper(replace(coalesce(document.code, ''), ' ', ''))
                        AND newer_document.version > document.version
                  }
                RETURN c.chunk_id AS chunk_id,
                       c.doc_id AS doc_id,
                       c.node_id AS node_id,
                       c.chunk_type AS chunk_type,
                       c.title AS title,
                       c.path_label AS path_label,
                       c.citation AS citation,
                       c.text AS text,
                       c.token_count AS token_count,
                       c.ordinal AS ordinal,
                       c.source_url AS source_url,
                       c.law_code AS law_code,
                       c.law_status AS law_status,
                       c.law_version AS law_version
                ORDER BY c.law_code, c.doc_id
                LIMIT $limit
                """,
                limit=max(1, int(limit)),
            ).data()

    def retrieve(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        query = normalize_space(query)
        if not query:
            return []
        candidates = self._neo4j_candidates(query, max(32, top_k * 5))
        if not candidates:
            return []

        scores: dict[str, float] = {}
        rows_by_chunk: dict[str, dict[str, Any]] = {}
        node_scores: dict[str, float] = {}
        for rank, row in enumerate(candidates, start=1):
            chunk_id = row["chunk_id"]
            score = score_chunk_payload(row, query, float(row.get("_score", 0.0)), rank)
            scores[chunk_id] = max(score, scores.get(chunk_id, -999.0))
            rows_by_chunk[chunk_id] = row
            node_id = row.get("node_id")
            if node_id:
                node_scores[node_id] = max(node_scores.get(node_id, 0.0), score)

        expanded_scores = self._expand_node_scores(node_scores)
        for row in self._chunks_for_nodes(expanded_scores.keys()):
            chunk_id = row["chunk_id"]
            score = expanded_scores.get(row["node_id"], 0.0)
            if row["chunk_type"] == "article":
                score += 0.08
            if score > scores.get(chunk_id, -999.0):
                scores[chunk_id] = score
                rows_by_chunk[chunk_id] = row

        selected = []
        for chunk_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
            row = dict(rows_by_chunk[chunk_id])
            row["score"] = round(float(score), 4)
            row["reasons"] = row.get("reasons") or ["neo4j"]
            selected.append(row)
            if len(selected) >= top_k:
                break
        for idx, row in enumerate(selected, start=1):
            row["source_id"] = f"S{idx}"
        return selected

    def _neo4j_candidates(self, query: str, limit: int) -> list[dict[str, Any]]:
        fulltext = neo4j_fulltext_query(query)
        try:
            with self.driver.session(database=self.config.neo4j_database) as session:
                rows = session.run(
                    """
                    CALL db.index.fulltext.queryNodes('legal_chunk_fulltext', $q)
                    YIELD node, score
                    MATCH (node)-[:CHUNK_OF]->(:LegalNode)-[:BELONGS_TO]->(document:LegalNode)
                    WHERE coalesce(node.law_version, node.version) = document.version
                      AND NOT EXISTS {
                          MATCH (newer_document:LegalNode)
                          WHERE newer_document.node_type = 'document'
                            AND toUpper(replace(coalesce(newer_document.code, ''), ' ', ''))
                                = toUpper(replace(coalesce(document.code, ''), ' ', ''))
                            AND newer_document.version > document.version
                      }
                    RETURN node.chunk_id AS chunk_id,
                           node.doc_id AS doc_id,
                           node.node_id AS node_id,
                           node.chunk_type AS chunk_type,
                           node.title AS title,
                           node.path_label AS path_label,
                           node.citation AS citation,
                           node.text AS text,
                           node.token_count AS token_count,
                           node.ordinal AS ordinal,
                           score AS _score
                    LIMIT $limit
                    """,
                    q=fulltext,
                    limit=limit,
                ).data()
        except Exception:
            terms = key_terms(query)[:6]
            needle = terms[0] if terms else strip_accents(query).lower()[:40]
            with self.driver.session(database=self.config.neo4j_database) as session:
                rows = session.run(
                    """
                    MATCH (node:LegalChunk)
                    MATCH (node)-[:CHUNK_OF]->(:LegalNode)-[:BELONGS_TO]->(document:LegalNode)
                    WHERE coalesce(node.law_version, node.version) = document.version
                      AND NOT EXISTS {
                          MATCH (newer_document:LegalNode)
                          WHERE newer_document.node_type = 'document'
                            AND toUpper(replace(coalesce(newer_document.code, ''), ' ', ''))
                                = toUpper(replace(coalesce(document.code, ''), ' ', ''))
                            AND newer_document.version > document.version
                      }
                      AND (
                           toLower(node.text) CONTAINS $needle
                        OR toLower(node.title) CONTAINS $needle
                        OR toLower(node.citation) CONTAINS $needle
                      )
                    RETURN node.chunk_id AS chunk_id,
                           node.doc_id AS doc_id,
                           node.node_id AS node_id,
                           node.chunk_type AS chunk_type,
                           node.title AS title,
                           node.path_label AS path_label,
                           node.citation AS citation,
                           node.text AS text,
                           node.token_count AS token_count,
                           node.ordinal AS ordinal,
                           1.0 AS _score
                    LIMIT $limit
                    """,
                    needle=needle,
                    limit=limit,
                ).data()
        for row in rows:
            row["reasons"] = ["neo4j_fulltext"]
        return rows

    def _expand_node_scores(self, node_scores: dict[str, float]) -> dict[str, float]:
        if not node_scores:
            return {}
        node_ids = list(node_scores)
        expanded = dict(node_scores)
        with self.driver.session(database=self.config.neo4j_database) as session:
            ancestor_rows = session.run(
                """
                MATCH (n:LegalNode)-[rels:BELONGS_TO*1..4]->(a:LegalNode)
                WHERE n.node_id IN $node_ids
                RETURN n.node_id AS source, a.node_id AS target, size(rels) AS depth
                """,
                node_ids=node_ids,
            ).data()
            outgoing_rows = session.run(
                """
                MATCH (n:LegalNode)-[r]->(m:LegalNode)
                WHERE n.node_id IN $node_ids AND type(r) IN $rels
                RETURN n.node_id AS source, m.node_id AS target, type(r) AS rel
                """,
                node_ids=node_ids,
                rels=GRAPH_EXPAND_RELS,
            ).data()
            incoming_rows = session.run(
                """
                MATCH (m:LegalNode)-[r]->(n:LegalNode)
                WHERE n.node_id IN $node_ids AND type(r) IN $rels
                RETURN n.node_id AS source, m.node_id AS target, type(r) AS rel
                """,
                node_ids=node_ids,
                rels=GRAPH_REVERSE_RELS,
            ).data()

        for row in ancestor_rows:
            source_score = node_scores.get(row["source"], 0.0)
            weight = max(0.32, 0.9 - (int(row["depth"]) - 1) * 0.12)
            expanded[row["target"]] = max(expanded.get(row["target"], 0.0), source_score * weight)

        rel_weights = {
            "CITES": 0.72,
            "GUIDES": 0.62,
            "AMENDS": 0.58,
            "REPLACES": 0.58,
            "BELONGS_TO": 0.45,
            "DEFINED_AS": 0.85,
            "APPLIES_TO": 0.75,
            "HAS_PARAMETER": 0.70,
            "SIGNS": 0.65,
            "PERFORMS": 0.72,
            "ENTITLED_TO": 0.80,
            "PROHIBITED_BY": 0.85,
            "STARTS_LIMITATION": 0.78,
            "TRANSITIONS_STATE": 0.75,
            "REQUIRES_CONDITION": 0.82,
            "INCLUDES_DOSSIER": 0.80,
            "SUBMITTED_AT": 0.70,
            "HAS_DURATION": 0.75,
            "NEXT_STAGE": 0.68,
            "TRIGGERS_OBLIGATION": 0.80,
            "CAUSES_RISK": 0.85,
            "MITIGATED_BY": 0.82,
            "APPLIES_ARTICLE": 0.85,
            "SIMILAR_FACTS": 0.88,
            "LEADS_TO_RULING": 0.85,
        }
        for row in outgoing_rows + incoming_rows:
            source_score = node_scores.get(row["source"], 0.0)
            weight = rel_weights.get(row["rel"], 0.4)
            expanded[row["target"]] = max(expanded.get(row["target"], 0.0), source_score * weight)
        return expanded

    def _chunks_for_nodes(self, node_ids: Iterable[str]) -> list[dict[str, Any]]:
        node_ids = list(dict.fromkeys(node_ids))
        if not node_ids:
            return []
        with self.driver.session(database=self.config.neo4j_database) as session:
            rows = session.run(
                """
                MATCH (c:LegalChunk)-[:CHUNK_OF]->(n:LegalNode)
                MATCH (n)-[:BELONGS_TO]->(document:LegalNode)
                WHERE n.node_id IN $node_ids
                  AND coalesce(c.law_version, c.version) = document.version
                  AND NOT EXISTS {
                      MATCH (newer_document:LegalNode)
                      WHERE newer_document.node_type = 'document'
                        AND toUpper(replace(coalesce(newer_document.code, ''), ' ', ''))
                            = toUpper(replace(coalesce(document.code, ''), ' ', ''))
                        AND newer_document.version > document.version
                  }
                RETURN c.chunk_id AS chunk_id,
                       c.doc_id AS doc_id,
                       c.node_id AS node_id,
                       c.chunk_type AS chunk_type,
                       c.title AS title,
                       c.path_label AS path_label,
                       c.citation AS citation,
                       c.text AS text,
                       c.token_count AS token_count,
                       c.ordinal AS ordinal
                ORDER BY
                    CASE c.chunk_type
                        WHEN 'article' THEN 0
                        WHEN 'clause' THEN 1
                        WHEN 'point' THEN 2
                        WHEN 'sliding' THEN 3
                        ELSE 4
                    END,
                    c.ordinal
                LIMIT 250
                """,
                node_ids=node_ids,
            ).data()
        for row in rows:
            row["reasons"] = ["neo4j_graph"]
        return rows


class Neo4jPostgresGraphRAGStore:
    def __init__(self, config: ExternalGraphRAGConfig | None = None):
        self.config = config or ExternalGraphRAGConfig.from_env()
        if not self.config.ready:
            raise RuntimeError(
                "Hybrid backend requires NEO4J_PASSWORD and DATABASE_URL."
            )
        self.rag = PostgresGraphRAGStore(self.config)
        self.postgres = self.rag.connection
        self.driver = neo4j_driver(self.config)
        try:
            self.driver.verify_connectivity()
        except Exception as exc:
            # Aura/network outages must not make the PostgreSQL index
            # unavailable. The driver remains open and retries on later calls.
            logger.warning(
                "Neo4j connectivity check failed; hybrid retrieval will "
                "temporarily fall back to PostgreSQL error_type=%s",
                type(exc).__name__,
            )

    def close(self) -> None:
        self.rag.close()
        self.driver.close()

    def stats(self) -> dict[str, Any]:
        try:
            with self.driver.session(database=self.config.neo4j_database) as session:
                row = session.run(
                    """
                    MATCH (d:LegalNode)
                    WHERE d.node_id STARTS WITH 'doc:'
                    WITH count(d) AS documents
                    MATCH (n:LegalNode)
                    WITH documents, count(n) AS nodes
                    MATCH ()-[r]->()
                    WHERE type(r) <> 'CHUNK_OF'
                    WITH documents, nodes, count(r) AS edges
                    MATCH (c:LegalChunk)
                    RETURN documents, nodes, edges, count(c) AS chunks
                    """
                ).single()
                rel_rows = session.run(
                    """
                    MATCH ()-[r]->()
                    WHERE type(r) <> 'CHUNK_OF'
                    RETURN type(r) AS relation, count(r) AS count
                    ORDER BY count DESC
                    """
                ).data()
                node_type_rows = session.run(
                    """
                    MATCH (n:LegalNode)
                    RETURN n.node_type AS node_type, count(n) AS count
                    ORDER BY count DESC
                    """
                ).data()
        except Exception as exc:
            logger.warning(
                "Neo4j stats unavailable; returning PostgreSQL stats "
                "error_type=%s",
                type(exc).__name__,
            )
            rag_stats = self.rag.stats()
            return {
                **rag_stats,
                "backend": "postgres_hybrid",
                "neo4j_available": False,
                "neo4j_uri": self.config.neo4j_uri,
            }
        rag_stats = self.rag.stats()
        return {
            "backend": "postgres_hybrid+neo4j_graphrag",
            "documents": row["documents"] if row else 0,
            "nodes": row["nodes"] if row else 0,
            "edges": row["edges"] if row else 0,
            "chunks": rag_stats["chunks"],
            "neo4j_chunks": row["chunks"] if row else 0,
            "relations": {item["relation"]: item["count"] for item in rel_rows},
            "node_types": {item["node_type"]: item["count"] for item in node_type_rows},
            "neo4j_uri": self.config.neo4j_uri,
            "neo4j_available": True,
            "retrieval": {
                "dense": "cosine",
                "lexical": "bm25",
                "fusion": "rrf",
                "graph": "neo4j",
            },
        }

    def document_structures(self, limit: int = 500) -> list[dict[str, Any]]:
        # PostgreSQL carries the same immutable structure chunks and remains
        # available when Neo4j Aura is temporarily unreachable.
        return self.rag.document_structures(limit)

    def retrieve(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        query = normalize_space(query)
        if not query:
            return []
        candidates = self._postgres_candidates(query, max(32, top_k * 5))
        if not candidates:
            return []

        scores: dict[str, float] = {}
        rows_by_chunk: dict[str, dict[str, Any]] = {}
        reasons_by_chunk: dict[str, list[str]] = {}
        node_scores: dict[str, float] = {}

        for row in candidates:
            chunk_id = row["chunk_id"]
            score = float(row.get("score", 0.0))
            scores[chunk_id] = max(score, scores.get(chunk_id, -999.0))
            rows_by_chunk[chunk_id] = row
            reasons_by_chunk[chunk_id] = list(dict.fromkeys(row.get("reasons", [])))
            node_id = row.get("node_id")
            if node_id:
                node_scores[node_id] = max(node_scores.get(node_id, 0.0), score)

        try:
            expanded_scores = self._expand_node_scores(node_scores)
            graph_node_ids = set(expanded_scores) - set(node_scores)
            expanded_rows = self._chunks_for_nodes(expanded_scores.keys())
        except Exception as exc:
            logger.warning(
                "Neo4j graph expansion failed; using PostgreSQL retrieval "
                "error_type=%s",
                type(exc).__name__,
            )
            selected = [dict(row) for row in candidates[:top_k]]
            for index, row in enumerate(selected, start=1):
                row["source_id"] = f"S{index}"
            return selected
        for row in expanded_rows:
            chunk_id = row["chunk_id"]
            score = expanded_scores.get(row["node_id"], 0.0)
            if row["chunk_type"] == "article":
                score += 0.08
            reasons = reasons_by_chunk.get(chunk_id, [])
            if row["node_id"] in graph_node_ids:
                reasons = list(dict.fromkeys([*reasons, "neo4j_graph"]))
            if score > scores.get(chunk_id, -999.0):
                scores[chunk_id] = score
                rows_by_chunk[chunk_id] = row
            if reasons:
                reasons_by_chunk[chunk_id] = reasons

        selected = []
        for chunk_id, score in sorted(scores.items(), key=lambda item: item[1], reverse=True):
            row = dict(rows_by_chunk[chunk_id])
            row["score"] = round(score, 4)
            row["reasons"] = reasons_by_chunk.get(chunk_id) or row.get("reasons") or ["neo4j_graph"]
            selected.append(row)
            if len(selected) >= top_k:
                break
        for idx, row in enumerate(selected, start=1):
            row["source_id"] = f"S{idx}"
        return selected

    def _postgres_candidates(self, query: str, limit: int) -> list[dict[str, Any]]:
        return self.rag.retrieve(query, limit)

    def _expand_node_scores(self, node_scores: dict[str, float]) -> dict[str, float]:
        if not node_scores:
            return {}
        node_ids = list(node_scores)
        expanded = dict(node_scores)
        with self.driver.session(database=self.config.neo4j_database) as session:
            ancestor_rows = session.run(
                """
                MATCH (n:LegalNode)-[rels:BELONGS_TO*1..4]->(a:LegalNode)
                WHERE n.node_id IN $node_ids
                RETURN n.node_id AS source, a.node_id AS target, size(rels) AS depth
                """,
                node_ids=node_ids,
            ).data()
            outgoing_rows = session.run(
                """
                MATCH (n:LegalNode)-[r]->(m:LegalNode)
                WHERE n.node_id IN $node_ids AND type(r) IN $rels
                RETURN n.node_id AS source, m.node_id AS target, type(r) AS rel
                """,
                node_ids=node_ids,
                rels=GRAPH_EXPAND_RELS,
            ).data()
            incoming_rows = session.run(
                """
                MATCH (m:LegalNode)-[r]->(n:LegalNode)
                WHERE n.node_id IN $node_ids AND type(r) IN $rels
                RETURN n.node_id AS source, m.node_id AS target, type(r) AS rel
                """,
                node_ids=node_ids,
                rels=GRAPH_REVERSE_RELS,
            ).data()

        for row in ancestor_rows:
            source_score = node_scores.get(row["source"], 0.0)
            weight = max(0.32, 0.9 - (int(row["depth"]) - 1) * 0.12)
            expanded[row["target"]] = max(expanded.get(row["target"], 0.0), source_score * weight)

        rel_weights = {
            "CITES": 0.72,
            "GUIDES": 0.62,
            "AMENDS": 0.58,
            "REPLACES": 0.58,
            "BELONGS_TO": 0.45,
            "DEFINED_AS": 0.85,
            "APPLIES_TO": 0.75,
            "HAS_PARAMETER": 0.70,
            "SIGNS": 0.65,
            "PERFORMS": 0.72,
            "ENTITLED_TO": 0.80,
            "PROHIBITED_BY": 0.85,
            "STARTS_LIMITATION": 0.78,
            "TRANSITIONS_STATE": 0.75,
            "REQUIRES_CONDITION": 0.82,
            "INCLUDES_DOSSIER": 0.80,
            "SUBMITTED_AT": 0.70,
            "HAS_DURATION": 0.75,
            "NEXT_STAGE": 0.68,
            "TRIGGERS_OBLIGATION": 0.80,
            "CAUSES_RISK": 0.85,
            "MITIGATED_BY": 0.82,
            "APPLIES_ARTICLE": 0.85,
            "SIMILAR_FACTS": 0.88,
            "LEADS_TO_RULING": 0.85,
        }
        for row in outgoing_rows + incoming_rows:
            source_score = node_scores.get(row["source"], 0.0)
            weight = rel_weights.get(row["rel"], 0.4)
            expanded[row["target"]] = max(expanded.get(row["target"], 0.0), source_score * weight)
        return expanded

    def _chunks_for_nodes(self, node_ids: Iterable[str]) -> list[dict[str, Any]]:
        node_ids = list(dict.fromkeys(node_ids))
        if not node_ids:
            return []
        with self.driver.session(database=self.config.neo4j_database) as session:
            rows = session.run(
                """
                MATCH (c:LegalChunk)-[:CHUNK_OF]->(n:LegalNode)
                MATCH (n)-[:BELONGS_TO]->(document:LegalNode)
                WHERE n.node_id IN $node_ids
                  AND coalesce(c.law_version, c.version) = document.version
                  AND NOT EXISTS {
                      MATCH (newer_document:LegalNode)
                      WHERE newer_document.node_type = 'document'
                        AND toUpper(replace(coalesce(newer_document.code, ''), ' ', ''))
                            = toUpper(replace(coalesce(document.code, ''), ' ', ''))
                        AND newer_document.version > document.version
                  }
                RETURN c.chunk_id AS chunk_id,
                       c.doc_id AS doc_id,
                       c.node_id AS node_id,
                       c.chunk_type AS chunk_type,
                       c.title AS title,
                       c.path_label AS path_label,
                       c.citation AS citation,
                       c.text AS text,
                       c.token_count AS token_count,
                       c.ordinal AS ordinal
                ORDER BY
                    CASE c.chunk_type
                        WHEN 'article' THEN 0
                        WHEN 'clause' THEN 1
                        WHEN 'point' THEN 2
                        WHEN 'sliding' THEN 3
                        ELSE 4
                    END,
                    c.ordinal
                LIMIT 250
                """,
                node_ids=node_ids,
            ).data()
        for row in rows:
            row["reasons"] = ["neo4j"]
        return rows

    def chunks_by_node(self, node_id: str, limit: int = 5) -> list[dict[str, Any]]:
        current_chunk = postgres_latest_chunk_predicate("current_chunk")
        with self.postgres.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT current_chunk.chunk_id, current_chunk.doc_id,
                       current_chunk.node_id, current_chunk.chunk_type,
                       current_chunk.title, current_chunk.path_label,
                       current_chunk.citation, current_chunk.text,
                       current_chunk.token_count, current_chunk.ordinal,
                       current_chunk.source_url, current_chunk.law_code,
                       current_chunk.law_status, current_chunk.law_version
                FROM graphrag_chunk AS current_chunk
                WHERE current_chunk.node_id = %s
                  AND {current_chunk}
                ORDER BY current_chunk.ordinal
                LIMIT %s
                """,
                (node_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
