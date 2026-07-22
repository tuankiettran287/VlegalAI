from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO_ID = "BAAI/bge-m3"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "models" / "bge-m3"
MARKER_FILE = ".vlegal-embedding-model.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Download the local semantic embedding checkpoint.")
    parser.add_argument("--repo-id", default=os.getenv("EMBEDDING_MODEL_REPO", DEFAULT_REPO_ID))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.getenv("EMBEDDING_MODEL_PATH", str(DEFAULT_OUTPUT_DIR))),
    )
    parser.add_argument("--revision", default=os.getenv("EMBEDDING_MODEL_REVISION", "main"))
    parser.add_argument("--token", default=os.getenv("HF_TOKEN") or None)
    return parser.parse_args()


def validate_checkpoint(model_dir: Path) -> None:
    required = ["config.json", "modules.json", "tokenizer_config.json"]
    missing = [name for name in required if not (model_dir / name).is_file()]
    has_safetensors = any(model_dir.rglob("*.safetensors"))
    has_pytorch_weights = any(model_dir.rglob("pytorch_model*.bin"))
    if not has_safetensors and not has_pytorch_weights:
        missing.append("*.safetensors or pytorch_model*.bin")
    if missing:
        raise RuntimeError("Embedding checkpoint is incomplete. Missing: " + ", ".join(missing))


def marker_matches(model_dir: Path, repo_id: str, revision: str) -> bool:
    try:
        marker = json.loads((model_dir / MARKER_FILE).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return marker.get("repo_id") == repo_id and marker.get("revision") == revision


def write_marker(model_dir: Path, repo_id: str, revision: str) -> None:
    temporary = model_dir / f"{MARKER_FILE}.tmp"
    temporary.write_text(
        json.dumps({"repo_id": repo_id, "revision": revision}, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(model_dir / MARKER_FILE)


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        validate_checkpoint(output_dir)
    except RuntimeError:
        pass
    else:
        if marker_matches(output_dir, args.repo_id, args.revision):
            print(f"Embedding checkpoint is already ready at: {output_dir}")
            return 0

    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(
            repo_id=args.repo_id,
            revision=args.revision,
            local_dir=output_dir,
            token=args.token,
        )
        validate_checkpoint(output_dir)
        write_marker(output_dir, args.repo_id, args.revision)
    except Exception as exc:
        print(f"Embedding model download failed: {exc}", file=sys.stderr)
        return 1

    print(f"Embedding checkpoint is ready at: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
