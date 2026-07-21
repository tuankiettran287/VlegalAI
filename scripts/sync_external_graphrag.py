from __future__ import annotations

import argparse
import json
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
    parser.add_argument("--db-path", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--storage-dir", type=Path, default=DEFAULT_STORAGE_DIR)
    parser.add_argument("--skip-sqlite-build", action="store_true")
    parser.add_argument("--reset-neo4j", action="store_true")
    parser.add_argument("--reset-postgres", action="store_true")
    args = parser.parse_args()

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
    )
    print("External GraphRAG synced:")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
