from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--renders", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--cols", type=int, default=4)
    parser.add_argument("--thumb-width", type=int, default=400)
    parser.add_argument("--start", type=int, default=1, help="First 1-based slide to include")
    parser.add_argument("--end", type=int, help="Last 1-based slide to include")
    args = parser.parse_args()

    render_dir = Path(args.renders)
    slides = sorted(
        render_dir.glob("Slide*.PNG"),
        key=lambda path: int(path.stem.replace("Slide", "")),
    )
    slides = [
        path
        for path in slides
        if args.start <= int(path.stem.replace("Slide", ""))
        and (args.end is None or int(path.stem.replace("Slide", "")) <= args.end)
    ]
    if not slides:
        raise SystemExit(f"No rendered slides found in {render_dir}")

    first = Image.open(slides[0])
    ratio = first.height / first.width
    thumb_w = args.thumb_width
    thumb_h = round(thumb_w * ratio)
    label_h = 28
    gutter = 14
    rows = math.ceil(len(slides) / args.cols)
    sheet_w = gutter + args.cols * (thumb_w + gutter)
    sheet_h = gutter + rows * (thumb_h + label_h + gutter)
    sheet = Image.new("RGB", (sheet_w, sheet_h), "#EAF0EC")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default()

    for index, slide_path in enumerate(slides):
        row, col = divmod(index, args.cols)
        x = gutter + col * (thumb_w + gutter)
        y = gutter + row * (thumb_h + label_h + gutter)
        with Image.open(slide_path) as image:
            thumb = image.convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        sheet.paste(thumb, (x, y))
        draw.rectangle((x, y, x + thumb_w, y + thumb_h), outline="#AFC8BA", width=2)
        slide_number = int(slide_path.stem.replace("Slide", ""))
        draw.text((x + 4, y + thumb_h + 6), f"Slide {slide_number}", fill="#17352D", font=font)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(output, quality=92)
    print(output)


if __name__ == "__main__":
    main()
