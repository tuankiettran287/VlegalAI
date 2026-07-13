from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.legal_graphrag import DEFAULT_DATA_DIR, DEFAULT_STORAGE_DIR, build_index


def main() -> None:
    parser = argparse.ArgumentParser(description="Build LaborCare legal GraphRAG index.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--storage-dir", type=Path, default=DEFAULT_STORAGE_DIR)
    args = parser.parse_args()

    stats = build_index(args.data_dir, args.storage_dir)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"Index written to: {args.storage_dir / 'legal_graphrag.sqlite'}")


if __name__ == "__main__":
    main()
