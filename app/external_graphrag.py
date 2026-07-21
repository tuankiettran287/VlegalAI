from __future__ import annotations

import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from neo4j import GraphDatabase
import psycopg
from psycopg.rows import dict_row
from sqlalchemy.engine import make_url

from app.legal_graphrag import DEFAULT_DB_PATH, hash_vector, key_terms, normalize_space, strip_accents


RELATION_TYPE_MAP = {
    "THUOC_VE": "BELONGS_TO",
    "HUONG_DAN": "GUIDES",
    "DAN_CHIEU_DEN": "CITES",
    "SUA_DOI": "AMENDS",
    "THAY_THE": "REPLACES",
    "BAN_HANH": "ISSUED_BY",
    # Layer 2: Legal Semantic Spectrum
    "DUOC_DINH_NGHIA_LA": "DEFINED_AS",
    "AP_DUNG_CHO": "APPLIES_TO",
    "CO_THAM_SO": "HAS_PARAMETER",
    # Layer 3: Domain Ontology
    "KY_KET": "SIGNS",
    "THUC_HIEN": "PERFORMS",
    "CO_QUYEN_HUONG": "ENTITLED_TO",
    "BI_NAM_TRONG_DANH_MUC_CAM": "PROHIBITED_BY",
    # Layer 4: Temporal & State Transition
    "BAT_DAU_TINH_THOI_HIEU": "STARTS_LIMITATION",
    "CHUYEN_TRANG_THAI": "TRANSITIONS_STATE",
    # Layer 5: Process-Oriented
    "YEU_CAU_DIEU_KIEN": "REQUIRES_CONDITION",
    "BAO_GOM_HO_SO": "INCLUDES_DOSSIER",
    "NOP_TAI": "SUBMITTED_AT",
    "CO_THOI_HAN_LA": "HAS_DURATION",
    # Layer 6: Lifecycle-Based
    "GIAI_DOAN_TIEP_THEO": "NEXT_STAGE",
    "KICH_HOAT_NGHIA_VU": "TRIGGERS_OBLIGATION",
    # Layer 7: Compliance & Risk Matrix
    "GAY_RA_RUI_RO": "CAUSES_RISK",
    "KHAC_PHUC_BANG": "MITIGATED_BY",
    # Layer 8: Precedent & Case-Based Reasoning
    "AP_DUNG_DIEU_LUAT": "APPLIES_ARTICLE",
    "CO_TINH_TIET_TUONG_TU": "SIMILAR_FACTS",
    "DAN_DEN_PHAN_QUYET": "LEADS_TO_RULING",
}

GRAPH_EXPAND_RELS = [
    "BELONGS_TO", "CITES", "GUIDES", "AMENDS", "REPLACES",
    "DEFINED_AS", "APPLIES_TO", "HAS_PARAMETER",
    "SIGNS", "PERFORMS", "ENTITLED_TO", "PROHIBITED_BY",
    "STARTS_LIMITATION", "TRANSITIONS_STATE",
    "REQUIRES_CONDITION", "INCLUDES_DOSSIER", "SUBMITTED_AT", "HAS_DURATION",
    "NEXT_STAGE", "TRIGGERS_OBLIGATION",
    "CAUSES_RISK", "MITIGATED_BY",
    "APPLIES_ARTICLE", "SIMILAR_FACTS", "LEADS_TO_RULING"
]
GRAPH_REVERSE_RELS = ["GUIDES", "AMENDS", "REPLACES"]


@dataclass(frozen=True)
class ExternalGraphRAGConfig:
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = ""
    neo4j_database: str = "neo4j"
    database_url: str = "postgresql+asyncpg://vlegal:vlegal@localhost:5432/vlegal"
    postgres_vector_size: int = 1536
    batch_size: int = 256

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
            postgres_vector_size=int(os.getenv("POSTGRES_VECTOR_SIZE", "1536")),
            batch_size=int(os.getenv("EXTERNAL_SYNC_BATCH_SIZE", "256")),
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


def postgres_dsn(database_url: str) -> str:
    """Convert SQLAlchemy async URLs to a DSN accepted by psycopg."""
    url = make_url(database_url)
    if not url.drivername.startswith("postgresql"):
        raise ValueError("DATABASE_URL must point to PostgreSQL")
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


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
    chunks = sqlite_rows(db_path, "chunks")

    driver = neo4j_driver(config)
    try:
        ensure_neo4j_schema(driver, config.neo4j_database)
        with driver.session(database=config.neo4j_database) as session:
            if reset:
                session.run("MATCH (c:LegalChunk) DETACH DELETE c")
                session.run("MATCH (n:LegalNode) DETACH DELETE n")

            for batch in batched(nodes, config.batch_size):
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
                        n.ordinal = row.ordinal
                    """,
                    rows=batch,
                )

            for batch in batched(chunks, config.batch_size):
                prepared = []
                for row in batch:
                    row = dict(row)
                    row.pop("vector", None)
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
                        c.ordinal = row.ordinal
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


def postgres_dense_vector(text: str, config: ExternalGraphRAGConfig) -> list[float]:
    return list(hash_vector(text, dims=config.postgres_vector_size))


def ensure_postgres_schema(config: ExternalGraphRAGConfig, reset: bool = False) -> None:
    if config.postgres_vector_size > 2000:
        raise ValueError("POSTGRES_VECTOR_SIZE must be <= 2000 when using an HNSW vector index")
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
                    embedding vector({config.postgres_vector_size}) NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_graphrag_chunk_doc_id ON graphrag_chunk (doc_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_graphrag_chunk_node_id ON graphrag_chunk (node_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS ix_graphrag_chunk_type ON graphrag_chunk (chunk_type)")
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
                cursor.execute("TRUNCATE TABLE graphrag_chunk")


def upsert_postgres_chunks(
    rows: Iterable[dict[str, Any]],
    config: ExternalGraphRAGConfig,
) -> int:
    prepared: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        vector_text = f"{row.get('title', '')}\n{row.get('path_label', '')}\n{row.get('text', '')}"
        row["embedding"] = vector_literal(postgres_dense_vector(vector_text, config))
        prepared.append(row)
    if not prepared:
        return 0

    statement = """
        INSERT INTO graphrag_chunk (
            chunk_id, doc_id, node_id, chunk_type, title, path_label, citation,
            text, token_count, ordinal, source_url, law_code, law_status,
            law_version, embedding, updated_at
        ) VALUES (
            %(chunk_id)s, %(doc_id)s, %(node_id)s, %(chunk_type)s,
            %(title)s, %(path_label)s, %(citation)s, %(text)s,
            %(token_count)s, %(ordinal)s, %(source_url)s, %(law_code)s,
            %(law_status)s, %(law_version)s, %(embedding)s::vector, now()
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
            embedding = EXCLUDED.embedding,
            updated_at = now()
    """
    with postgres_connection(config) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(statement, prepared)
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

    chunks = sqlite_rows(db_path, "chunks")
    ensure_postgres_schema(config, reset=reset)

    total = 0
    for batch in batched(chunks, config.batch_size):
        rows = []
        for row in batch:
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
                "source_url": None,
                "law_code": None,
                "law_status": None,
                "law_version": None,
            })
        total += upsert_postgres_chunks(rows, config)

    return {"chunks": total}


def sync_external_graphrag(
    db_path: Path | str = DEFAULT_DB_PATH,
    config: ExternalGraphRAGConfig | None = None,
    reset_neo4j: bool = False,
    reset_postgres: bool = False,
) -> dict[str, Any]:
    config = config or ExternalGraphRAGConfig.from_env()
    res = {}
    try:
        res["neo4j"] = sync_neo4j(db_path, config, reset=reset_neo4j)
    except Exception as exc:
        res["neo4j"] = {"error": f"{type(exc).__name__}: {exc}"}
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
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM graphrag_chunk LIMIT 1")

    def close(self) -> None:
        self.connection.close()

    def stats(self) -> dict[str, Any]:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT count(*) AS chunks, count(DISTINCT doc_id) AS documents FROM graphrag_chunk")
            counts = cursor.fetchone() or {"chunks": 0, "documents": 0}
        return {
            "backend": "postgres",
            "documents": counts["documents"],
            "nodes": 0,
            "edges": 0,
            "chunks": counts["chunks"],
            "relations": {},
        }

    def retrieve(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        query = normalize_space(query)
        if not query:
            return []
        query_vector = vector_literal(postgres_dense_vector(query, self.config))
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT chunk_id, doc_id, node_id, chunk_type, title, path_label,
                       citation, text, token_count, ordinal, source_url,
                       1 - (embedding <=> %s::vector) AS _score
                FROM graphrag_chunk
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_vector, query_vector, max(24, top_k * 4)),
            )
            candidates = cursor.fetchall()
        rows = []
        for rank, source in enumerate(candidates, start=1):
            row = dict(source)
            row["score"] = score_chunk_payload(row, query, float(row.pop("_score", 0.0)), rank)
            row["reasons"] = ["postgres_vector"]
            rows.append(row)
        rows.sort(key=lambda row: row["score"], reverse=True)
        selected = rows[:top_k]
        for idx, row in enumerate(selected, start=1):
            row["source_id"] = f"S{idx}"
            row["score"] = round(float(row["score"]), 4)
        return selected


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
                    WHERE toLower(node.text) CONTAINS $needle
                       OR toLower(node.title) CONTAINS $needle
                       OR toLower(node.citation) CONTAINS $needle
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
                WHERE n.node_id IN $node_ids
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
        self.postgres = postgres_connection(self.config)
        self.driver = neo4j_driver(self.config)
        self.driver.verify_connectivity()
        with self.postgres.cursor() as cursor:
            cursor.execute("SELECT 1 FROM graphrag_chunk LIMIT 1")

    def close(self) -> None:
        self.postgres.close()
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
        with self.postgres.cursor() as cursor:
            cursor.execute("SELECT count(*) AS count FROM graphrag_chunk")
            postgres_count = (cursor.fetchone() or {"count": 0})["count"]
        return {
            "backend": "neo4j+postgres",
            "documents": row["documents"] if row else 0,
            "nodes": row["nodes"] if row else 0,
            "edges": row["edges"] if row else 0,
            "chunks": postgres_count,
            "neo4j_chunks": row["chunks"] if row else 0,
            "relations": {item["relation"]: item["count"] for item in rel_rows},
            "node_types": {item["node_type"]: item["count"] for item in node_type_rows},
            "neo4j_uri": self.config.neo4j_uri,
        }

    def retrieve(self, query: str, top_k: int = 10) -> list[dict[str, Any]]:
        query = normalize_space(query)
        if not query:
            return []
        candidates = self._postgres_candidates(query, max(32, top_k * 5))
        if not candidates:
            return []

        scores: dict[str, float] = {}
        rows_by_chunk: dict[str, dict[str, Any]] = {}
        node_scores: dict[str, float] = {}
        query_ascii = strip_accents(query).lower()
        terms = key_terms(query)

        for rank, row in enumerate(candidates, start=1):
            chunk_id = row["chunk_id"]
            haystack = strip_accents(f"{row.get('title', '')} {row.get('citation', '')} {row.get('text', '')[:700]}").lower()
            score = float(row.get("_score", 0.0)) * (1.0 / max(1.0, rank ** 0.35))
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

            scores[chunk_id] = max(score, scores.get(chunk_id, -999.0))
            rows_by_chunk[chunk_id] = row
            node_id = row.get("node_id")
            if node_id:
                node_scores[node_id] = max(node_scores.get(node_id, 0.0), score)

        expanded_scores = self._expand_node_scores(node_scores)
        expanded_rows = self._chunks_for_nodes(expanded_scores.keys())
        for row in expanded_rows:
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
            row["score"] = round(score, 4)
            row["reasons"] = row.get("reasons") or ["postgres_vector", "neo4j"]
            selected.append(row)
            if len(selected) >= top_k:
                break
        for idx, row in enumerate(selected, start=1):
            row["source_id"] = f"S{idx}"
        return selected

    def _postgres_candidates(self, query: str, limit: int) -> list[dict[str, Any]]:
        query_vector = vector_literal(postgres_dense_vector(query, self.config))
        with self.postgres.cursor() as cursor:
            cursor.execute(
                """
                SELECT chunk_id, doc_id, node_id, chunk_type, title, path_label,
                       citation, text, token_count, ordinal, source_url,
                       1 - (embedding <=> %s::vector) AS _score
                FROM graphrag_chunk
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (query_vector, query_vector, limit),
            )
            rows = [dict(row) for row in cursor.fetchall()]
        for row in rows:
            row["reasons"] = ["postgres_vector"]
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
                WHERE n.node_id IN $node_ids
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
        with self.postgres.cursor() as cursor:
            cursor.execute(
                """
                SELECT chunk_id, doc_id, node_id, chunk_type, title, path_label,
                       citation, text, token_count, ordinal, source_url
                FROM graphrag_chunk
                WHERE node_id = %s
                ORDER BY ordinal
                LIMIT %s
                """,
                (node_id, limit),
            )
            return [dict(row) for row in cursor.fetchall()]
