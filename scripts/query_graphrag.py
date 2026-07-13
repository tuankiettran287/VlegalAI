from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.legal_graphrag import GraphRAGStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Query the LaborCare GraphRAG index.")
    parser.add_argument("query", nargs="+")
    parser.add_argument("--top-k", type=int, default=8)
    args = parser.parse_args()

    store = GraphRAGStore()
    results = store.retrieve(" ".join(args.query), top_k=args.top_k)
    for result in results:
        print(f"[{result['source_id']}] score={result['score']} type={result['chunk_type']}")
        print(result["citation"])
        print(result["text"][:700].replace("\n", " "))
        print()


if __name__ == "__main__":
    main()
