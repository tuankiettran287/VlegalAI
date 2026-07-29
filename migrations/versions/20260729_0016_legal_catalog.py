"""Create a queryable catalogue of the indexed VLegal corpus."""

from alembic import op


revision = "20260729_0016"
down_revision = "20260729_0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE MATERIALIZED VIEW legal_catalog_corpus AS
        WITH latest_chunks AS (
            SELECT
                upper(
                    regexp_replace(
                        btrim(chunk.law_code),
                        '[[:space:]]+',
                        '',
                        'g'
                    )
                ) AS law_code_normalized,
                chunk.law_code,
                chunk.title,
                chunk.path_label,
                chunk.citation,
                chunk.source_url,
                chunk.law_status,
                chunk.law_version,
                chunk.chunk_type,
                chunk.ordinal,
                chunk.updated_at
            FROM graphrag_chunk AS chunk
            INNER JOIN graphrag_law_version AS latest_law
                ON latest_law.law_code_normalized = upper(
                    regexp_replace(
                        btrim(chunk.law_code),
                        '[[:space:]]+',
                        '',
                        'g'
                    )
                )
               AND latest_law.latest_version = chunk.law_version
            WHERE chunk.law_code IS NOT NULL
              AND btrim(chunk.law_code) <> ''
        ),
        representative AS (
            SELECT DISTINCT ON (law_code_normalized)
                law_code_normalized,
                law_code AS code,
                coalesce(
                    nullif(btrim(title), ''),
                    nullif(btrim(path_label), ''),
                    law_code
                ) AS title,
                source_url,
                coalesce(nullif(upper(btrim(law_status)), ''), 'UNKNOWN')
                    AS corpus_status,
                law_version,
                updated_at AS indexed_at
            FROM latest_chunks
            ORDER BY
                law_code_normalized,
                CASE chunk_type
                    WHEN 'document_intro' THEN 0
                    WHEN 'article' THEN 1
                    WHEN 'clause' THEN 2
                    ELSE 3
                END,
                ordinal,
                updated_at DESC
        ),
        counts AS (
            SELECT law_code_normalized, count(*)::bigint AS chunk_count
            FROM latest_chunks
            GROUP BY law_code_normalized
        )
        SELECT
            representative.law_code_normalized,
            representative.code,
            representative.title,
            CASE
                WHEN representative.code ILIKE '%NĐ-CP'
                  OR representative.code ILIKE '%ND-CP'
                  OR representative.title ILIKE 'NGHỊ ĐỊNH%'
                    THEN 'DECREE'
                WHEN representative.code ILIKE '%/TT-%'
                  OR representative.title ILIKE 'THÔNG TƯ%'
                    THEN 'CIRCULAR'
                WHEN representative.title ILIKE 'BỘ LUẬT%'
                    THEN 'CODE'
                WHEN representative.code ILIKE '%QH%'
                  OR representative.title ILIKE 'LUẬT%'
                    THEN 'LAW'
                WHEN representative.code ILIKE '%/VBHN-%'
                  OR representative.title ILIKE 'VĂN BẢN HỢP NHẤT%'
                    THEN 'CONSOLIDATED'
                WHEN representative.title ILIKE 'NGHỊ QUYẾT%'
                    THEN 'RESOLUTION'
                WHEN representative.title ILIKE 'QUYẾT ĐỊNH%'
                    THEN 'DECISION'
                ELSE 'OTHER'
            END AS document_type,
            representative.source_url,
            representative.corpus_status,
            representative.law_version,
            counts.chunk_count,
            representative.indexed_at,
            now() AS refreshed_at
        FROM representative
        INNER JOIN counts USING (law_code_normalized)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX ix_legal_catalog_corpus_code
        ON legal_catalog_corpus (law_code_normalized)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_legal_catalog_corpus_type
        ON legal_catalog_corpus (document_type)
        """
    )
    op.execute(
        """
        CREATE INDEX ix_legal_catalog_corpus_status
        ON legal_catalog_corpus (corpus_status)
        """
    )


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW IF EXISTS legal_catalog_corpus")
