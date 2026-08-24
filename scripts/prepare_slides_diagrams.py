from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "diagramv2" / "png"
OUTPUT = ROOT / "tmp" / "slides-assets"
CANVAS = (2460, 1000)
BACKGROUND = (248, 251, 249)


def contain(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    copy = image.convert("RGB")
    copy.thumbnail(size, Image.Resampling.LANCZOS)
    return copy


def paste_center(
    canvas: Image.Image,
    image: Image.Image,
    box: tuple[int, int, int, int],
) -> None:
    left, top, right, bottom = box
    fitted = contain(image, (right - left, bottom - top))
    x = left + (right - left - fitted.width) // 2
    y = top + (bottom - top - fitted.height) // 2
    canvas.paste(fitted, (x, y))


def build_inventory() -> None:
    source = Image.open(SOURCE / "23-cloud-sql-complete-schema.png").convert("RGB")
    canvas = Image.new("RGB", CANVAS, BACKGROUND)
    gap = 32
    margin = 18
    panel_width = (CANVAS[0] - 2 * margin - 2 * gap) // 3
    boundaries = [0, source.height // 3, (2 * source.height) // 3, source.height]
    for index in range(3):
        crop = source.crop((0, boundaries[index], source.width, boundaries[index + 1]))
        crop = ImageOps.expand(crop, border=2, fill=(211, 230, 220))
        left = margin + index * (panel_width + gap)
        paste_center(canvas, crop, (left, 10, left + panel_width, CANVAS[1] - 10))
    canvas.save(OUTPUT / "23-cloud-sql-complete-schema-wide.png", optimize=True)


def build_identity() -> None:
    source = Image.open(SOURCE / "04-postgres-erd-identity-chat.png").convert("RGB")
    canvas = Image.new("RGB", CANVAS, BACKGROUND)
    paste_center(canvas, source, (10, 10, CANVAS[0] - 10, CANVAS[1] - 10))
    canvas.save(OUTPUT / "04-postgres-erd-identity-chat-wide.png", optimize=True)


def build_content_runtime() -> None:
    source = Image.open(SOURCE / "05-postgres-erd-content-runtime.png").convert("RGB")
    canvas = Image.new("RGB", CANVAS, BACKGROUND)

    # The source is intentionally ultra-wide. Preserve three overlapping
    # database domains as zoom panels so field names remain readable.
    panels = (
        source.crop((0, 0, 4700, source.height)),
        source.crop((4000, 0, 8500, source.height)),
        source.crop((7900, 0, source.width, source.height)),
    )
    gap = 28
    margin = 10
    panel_width = (CANVAS[0] - 2 * margin - 2 * gap) // 3
    for index, panel in enumerate(panels):
        left = margin + index * (panel_width + gap)
        paste_center(canvas, panel, (left, 10, left + panel_width, CANVAS[1] - 10))
    canvas.save(OUTPUT / "05-postgres-erd-content-runtime-wide.png", optimize=True)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    build_inventory()
    build_identity()
    build_content_runtime()
    print(f"Prepared diagram assets in {OUTPUT}")


if __name__ == "__main__":
    main()
