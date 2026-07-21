from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO_ID = "Qwen/Qwen3-14B"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "models" / "Qwen3-14B"
RECOMMENDED_FREE_BYTES = 35 * 1024**3
MARKER_FILE = ".vlegal-model.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a complete Qwen checkpoint from Hugging Face."
    )
    parser.add_argument(
        "--repo-id",
        default=os.getenv("QWEN_MODEL_REPO", DEFAULT_REPO_ID),
        help=f"Hugging Face model repository (default: {DEFAULT_REPO_ID}).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.getenv("QWEN_MODEL_PATH", str(DEFAULT_OUTPUT_DIR))),
        help=f"Destination directory (default: {DEFAULT_OUTPUT_DIR}).",
    )
    parser.add_argument(
        "--revision",
        default=os.getenv("QWEN_MODEL_REVISION", "main"),
        help="Branch, tag, or commit to download (default: main).",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("HF_TOKEN") or None,
        help="Optional Hugging Face token. Defaults to the HF_TOKEN environment variable.",
    )
    return parser.parse_args()


def marker_matches(model_dir: Path, repo_id: str, revision: str) -> bool:
    marker_path = model_dir / MARKER_FILE
    if not marker_path.is_file():
        return False
    try:
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return marker.get("repo_id") == repo_id and marker.get("revision") == revision


def write_marker(model_dir: Path, repo_id: str, revision: str) -> None:
    marker_path = model_dir / MARKER_FILE
    temporary_path = model_dir / f"{MARKER_FILE}.tmp"
    temporary_path.write_text(
        json.dumps({"repo_id": repo_id, "revision": revision}, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.replace(marker_path)


def validate_checkpoint(model_dir: Path) -> None:
    missing: list[str] = []

    if not (model_dir / "config.json").is_file():
        missing.append("config.json")
    if not (model_dir / "tokenizer_config.json").is_file():
        missing.append("tokenizer_config.json")
    if not any(
        (model_dir / name).is_file()
        for name in ("tokenizer.json", "tokenizer.model")
    ):
        missing.append("tokenizer.json or tokenizer.model")
    if not any(model_dir.glob("*.safetensors")):
        missing.append("*.safetensors")

    if missing:
        raise RuntimeError(
            "The downloaded checkpoint is incomplete. Missing: " + ", ".join(missing)
        )


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
            print(f"Checkpoint is already ready at: {output_dir}")
            return 0
        if not (output_dir / MARKER_FILE).exists():
            write_marker(output_dir, args.repo_id, args.revision)
            print(f"Existing checkpoint accepted at: {output_dir}")
            return 0

    free_bytes = shutil.disk_usage(output_dir).free
    if free_bytes < RECOMMENDED_FREE_BYTES:
        print(
            f"Warning: only {free_bytes / 1024**3:.1f} GiB is free. "
            f"At least {RECOMMENDED_FREE_BYTES / 1024**3:.0f} GiB is recommended.",
            file=sys.stderr,
        )

    # The application image is offline by default. This dedicated downloader is
    # the only entry point that deliberately enables Hugging Face network access.
    os.environ.pop("HF_HUB_OFFLINE", None)
    os.environ.pop("TRANSFORMERS_OFFLINE", None)

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print(
            "Missing huggingface_hub. Install it with:\n"
            "  python -m pip install --upgrade huggingface_hub",
            file=sys.stderr,
        )
        return 1

    print(f"Repository : {args.repo_id}")
    print(f"Revision   : {args.revision}")
    print(f"Destination: {output_dir}")
    print("Downloading; interrupted downloads can be resumed by running this command again.")

    try:
        snapshot_download(
            repo_id=args.repo_id,
            revision=args.revision,
            local_dir=output_dir,
            token=args.token,
        )
        validate_checkpoint(output_dir)
        write_marker(output_dir, args.repo_id, args.revision)
    except Exception as exc:
        print(f"Download failed: {exc}", file=sys.stderr)
        return 1

    size_bytes = sum(
        path.stat().st_size for path in output_dir.rglob("*") if path.is_file()
    )
    print(f"Download completed: {size_bytes / 1024**3:.2f} GiB")
    print(f"Checkpoint is ready at: {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
