from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image


def longest_run(mask: np.ndarray) -> tuple[int, int]:
    best_start = best_end = current_start = 0
    in_run = False
    for index, value in enumerate(mask.tolist() + [False]):
        if value and not in_run:
            current_start = index
            in_run = True
        elif not value and in_run:
            if index - current_start > best_end - best_start:
                best_start, best_end = current_start, index
            in_run = False
    return best_start, best_end


def detect_page(image: Image.Image) -> tuple[int, int, int, int]:
    rgb = np.asarray(image.convert("RGB"))
    height, width, _ = rgb.shape

    bright = np.all(rgb > 235, axis=2)
    # Page content can contain wide colored banners and tables, so only require
    # enough white margin/background to distinguish it from Word's dark canvas.
    candidate_rows = bright.sum(axis=1) > 50
    candidate_rows[: min(110, height)] = False
    top, bottom = longest_run(candidate_rows)
    if bottom - top < 250:
        raise ValueError("No document page-sized bright row region was detected.")

    row_region = bright[top:bottom]
    candidate_cols = row_region.sum(axis=0) > max(50, int((bottom - top) * 0.35))
    left, right = longest_run(candidate_cols)
    if right - left < 250:
        raise ValueError("No document page-sized bright column region was detected.")

    # Include the antialiased page edge while staying inside the dark Word canvas.
    pad = 2
    return (
        max(0, left - pad),
        max(0, top - pad),
        min(width, right + pad),
        min(height, bottom + pad),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for existing in args.output_dir.glob("page-*.png"):
        existing.unlink()

    results: list[str] = []
    for path in sorted(args.input_dir.glob("page-*-raw.png")):
        with Image.open(path) as image:
            box = detect_page(image)
            cropped = image.crop(box)
            destination = args.output_dir / path.name.replace("-raw", "")
            cropped.save(destination)
            results.append(
                f"{destination.name}: {cropped.width}x{cropped.height} crop={box}"
            )

    if not results:
        raise SystemExit("No raw Word page captures were found.")
    print("\n".join(results))


if __name__ == "__main__":
    main()
