from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv

from app.external_graphrag import ExternalGraphRAGConfig, sync_external_graphrag
from app.legal_graphrag import DEFAULT_DATA_DIR, DEFAULT_DB_PATH, DEFAULT_STORAGE_DIR, build_index


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env", override=True)
    parser = argparse.ArgumentParser(
        description="Sync VLegalAI GraphRAG to Neo4j and PostgreSQL pgvector."
    )
    parser.add_argument(
        "--db-path",
        type=Path,
        default=Path(os.getenv("LEGAL_GRAPHRAG_DB", str(DEFAULT_DB_PATH))),
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.getenv("LEGAL_DATA_DIR", str(DEFAULT_DATA_DIR))),
    )
    parser.add_argument(
        "--storage-dir",
        type=Path,
        default=Path(os.getenv("LEGAL_STORAGE_DIR", str(DEFAULT_STORAGE_DIR))),
    )
    parser.add_argument("--skip-sqlite-build", action="store_true")
    parser.add_argument("--reset-neo4j", action="store_true")
    parser.add_argument("--reset-postgres", action="store_true")
    parser.add_argument("--skip-neo4j", action="store_true")
    parser.add_argument("--skip-postgres", action="store_true")
    args = parser.parse_args()

    if args.skip_neo4j and args.skip_postgres:
        parser.error("Cannot skip both Neo4j and PostgreSQL.")

    if not args.skip_sqlite_build:
        build_stats = build_index(args.data_dir, args.storage_dir)
        print("SQLite GraphRAG rebuilt:")
        print(json.dumps(build_stats, ensure_ascii=False, indent=2))

    config = ExternalGraphRAGConfig.from_env()
    result = sync_external_graphrag(
        args.db_path,
        config=config,
        reset_neo4j=args.reset_neo4j,
        reset_postgres=args.reset_postgres,
        include_neo4j=not args.skip_neo4j,
        include_postgres=not args.skip_postgres,
    )
    print("External GraphRAG synced:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    failures = [name for name, value in result.items() if isinstance(value, dict) and value.get("error")]
    if failures:
        raise SystemExit(f"External GraphRAG sync failed for: {', '.join(failures)}")


if __name__ == "__main__":
    main()
