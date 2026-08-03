"""Build the silent, captioned VLegal landing-page walkthrough.

Install the local encoder once with:
    python -m pip install --target .local-tools/video imageio-ffmpeg

Then run:
    $env:PYTHONPATH='.local-tools/video'; python scripts/media/build_landing_guide.py
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

try:
    import imageio_ffmpeg
except ImportError as exc:  # pragma: no cover - local media tooling only
    raise SystemExit(
        "Install imageio-ffmpeg into .local-tools/video before building the guide."
    ) from exc


ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "frontend" / "public"
OUTPUT = PUBLIC / "vlegal-guide.mp4"
POSTER = PUBLIC / "vlegal-guide-poster.jpg"

WIDTH, HEIGHT = 1280, 720
FPS = 24
DURATION_SECONDS = 30

CANVAS = "#f7f5ef"
PAPER = "#fffefa"
INK = "#102e2b"
DEEP = "#073b38"
BRAND = "#087f72"
MINT = "#dceee9"
MUTED = "#60736f"
LINE = "#d6ddd9"
GOLD = "#c69a4b"
WHITE = "#ffffff"

FONT_REGULAR = Path(r"C:\Windows\Fonts\segoeui.ttf")
FONT_BOLD = Path(r"C:\Windows\Fonts\segoeuib.ttf")
# Segoe UI covers the complete Vietnamese character set used by the guide.
FONT_SERIF = Path(r"C:\Windows\Fonts\segoeuib.ttf")


def font(size: int, *, bold: bool = False, serif: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_SERIF if serif and FONT_SERIF.exists() else (FONT_BOLD if bold else FONT_REGULAR)
    return ImageFont.truetype(str(path), size=size)


def smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3 - 2 * value)


def scene_alpha(local_time: float, duration: float) -> int:
    fade_in = smoothstep(local_time / 0.38)
    fade_out = smoothstep((duration - local_time) / 0.38)
    return round(255 * min(fade_in, fade_out))


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str, outline: str | None = None, width: int = 1) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int, fill: str, *, bold: bool = False, serif: bool = False, anchor: str | None = None) -> None:
    draw.text(xy, value, font=font(size, bold=bold, serif=serif), fill=fill, anchor=anchor)


def wrap_lines(draw: ImageDraw.ImageDraw, value: str, max_width: int, size: int, *, bold: bool = False, serif: bool = False) -> list[str]:
    current = ""
    lines: list[str] = []
    selected_font = font(size, bold=bold, serif=serif)
    for word in value.split():
        candidate = f"{current} {word}".strip()
        if draw.textbbox((0, 0), candidate, font=selected_font)[2] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def paragraph(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, max_width: int, size: int, fill: str, *, line_gap: int = 8, bold: bool = False, serif: bool = False) -> int:
    x, y = xy
    lines = wrap_lines(draw, value, max_width, size, bold=bold, serif=serif)
    line_height = size + line_gap
    for index, line in enumerate(lines):
        draw_text(draw, (x, y + index * line_height), line, size, fill, bold=bold, serif=serif)
    return y + len(lines) * line_height


def draw_scale(draw: ImageDraw.ImageDraw, center: tuple[int, int], size: int, color: str, width: int = 4) -> None:
    x, y = center
    top = y - size // 2
    bottom = y + size // 2
    draw.line((x, top, x, bottom), fill=color, width=width)
    draw.line((x - size // 3, bottom, x + size // 3, bottom), fill=color, width=width)
    draw.line((x - size // 2, top + size // 4, x + size // 2, top + size // 4), fill=color, width=width)
    for direction in (-1, 1):
        pan_x = x + direction * size // 2
        bar_y = top + size // 4
        draw.line((pan_x, bar_y, pan_x - direction * size // 6, bar_y + size // 3), fill=color, width=max(2, width - 1))
        draw.line((pan_x, bar_y, pan_x + direction * size // 6, bar_y + size // 3), fill=color, width=max(2, width - 1))
        draw.arc((pan_x - size // 5, bar_y + size // 4, pan_x + size // 5, bar_y + size // 2), 0, 180, fill=color, width=max(2, width - 1))


def draw_brand(draw: ImageDraw.ImageDraw, *, inverse: bool = False) -> None:
    fill = PAPER if not inverse else "#0b4541"
    icon = GOLD if inverse else "#f5ddb0"
    rounded(draw, (54, 38, 104, 88), 14, fill)
    draw_scale(draw, (79, 63), 27, icon, 3)
    draw_text(draw, (119, 46), "VLegal", 24, WHITE if inverse else INK, bold=True)
    draw_text(draw, (119, 73), "LEGAL INTELLIGENCE", 10, "#8bd2c5" if inverse else MUTED, bold=True)


def draw_progress(draw: ImageDraw.ImageDraw, progress: float, *, inverse: bool = False) -> None:
    bar_color = "#315653" if inverse else "#d8dfdc"
    draw.rounded_rectangle((54, 682, 1226, 687), radius=3, fill=bar_color)
    draw.rounded_rectangle((54, 682, 54 + int(1172 * progress), 687), radius=3, fill="#58b8a5" if inverse else BRAND)
    draw_text(draw, (1226, 660), f"{round(progress * DURATION_SECONDS):02d} / {DURATION_SECONDS}s", 10, "#91aaa5" if inverse else MUTED, anchor="ra")


def base_frame(progress: float, *, inverse: bool = False) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), DEEP if inverse else CANVAS)
    draw = ImageDraw.Draw(image)
    if inverse:
        draw.ellipse((870, -180, 1390, 340), outline="#18534f", width=2)
        draw.ellipse((-160, 430, 260, 850), outline="#18534f", width=2)
    else:
        draw.ellipse((918, -210, 1400, 272), outline="#cae1db", width=2)
        draw.ellipse((-170, 475, 200, 845), outline="#d6e5e0", width=2)
    draw_brand(draw, inverse=inverse)
    draw_text(draw, (1226, 58), "HƯỚNG DẪN SỬ DỤNG · 2026", 11, "#8bd2c5" if inverse else BRAND, bold=True, anchor="ra")
    draw_progress(draw, progress, inverse=inverse)
    return image


def scene_intro(local: float, duration: float, global_progress: float) -> Image.Image:
    image = base_frame(global_progress, inverse=True)
    draw = ImageDraw.Draw(image)
    lift = int(22 * (1 - smoothstep(local / 1.0)))
    draw_text(draw, (640, 230 + lift), "BẮT ĐẦU VỚI", 14, "#74c8b8", bold=True, anchor="mm")
    draw_text(draw, (640, 310 + lift), "VLegal AI", 72, WHITE, bold=True, serif=True, anchor="mm")
    draw_text(draw, (640, 380 + lift), "Hiểu đúng quy định. Vững vàng quyết định.", 25, "#c4d8d4", anchor="mm")
    rounded(draw, (490, 438, 790, 492), 27, "#fffefa")
    draw_text(draw, (640, 465), "Hướng dẫn trong 30 giây", 15, DEEP, bold=True, anchor="mm")
    return image


def scene_login(local: float, duration: float, global_progress: float) -> Image.Image:
    image = base_frame(global_progress)
    draw = ImageDraw.Draw(image)
    reveal = smoothstep(local / 0.9)
    draw_text(draw, (74, 164), "BƯỚC 1", 12, BRAND, bold=True)
    draw_text(draw, (74, 205), "Đăng nhập bằng Google", 43, INK, bold=True, serif=True)
    paragraph(draw, (74, 269), "Dùng tài khoản Google để lưu lịch sử hội thoại và tài liệu trong cùng một không gian.", 450, 18, MUTED, line_gap=10)
    x_offset = int(70 * (1 - reveal))
    card = (678 + x_offset, 154, 1178 + x_offset, 595)
    rounded(draw, card, 26, PAPER, LINE, 2)
    draw_text(draw, (928 + x_offset, 208), "Chào mừng đến VLegal", 28, INK, bold=True, anchor="mm")
    draw_text(draw, (928 + x_offset, 247), "Trợ lý pháp lý có căn cứ", 15, MUTED, anchor="mm")
    rounded(draw, (748 + x_offset, 303, 1108 + x_offset, 369), 33, DEEP)
    rounded(draw, (764 + x_offset, 319, 798 + x_offset, 353), 17, WHITE)
    draw_text(draw, (781 + x_offset, 336), "G", 17, "#4285f4", bold=True, anchor="mm")
    draw_text(draw, (827 + x_offset, 336), "Tiếp tục với Google", 16, WHITE, bold=True, anchor="lm")
    if local > 2.3:
        opacity = smoothstep((local - 2.3) / 0.6)
        check_color = BRAND if opacity > 0.5 else "#9fbdb7"
        rounded(draw, (748 + x_offset, 402, 1108 + x_offset, 500), 18, "#f2f7f5", "#cbe0da")
        draw_text(draw, (774 + x_offset, 426), "TÔI NÊN GỌI BẠN LÀ GÌ?", 10, check_color, bold=True)
        draw_text(draw, (774 + x_offset, 461), "Tên hoặc biệt danh của bạn", 16, INK)
    draw_text(draw, (74, 562), "Không cần tạo thêm mật khẩu.", 14, BRAND, bold=True)
    return image


def draw_app_shell(draw: ImageDraw.ImageDraw) -> None:
    rounded(draw, (56, 116, 1224, 632), 24, PAPER, LINE, 2)
    rounded(draw, (56, 116, 276, 632), 24, DEEP)
    draw.rectangle((252, 116, 276, 632), fill=DEEP)
    rounded(draw, (78, 144, 126, 192), 13, "#f7e8c8")
    draw_scale(draw, (102, 168), 26, DEEP, 3)
    draw_text(draw, (140, 151), "VLegal", 20, WHITE, bold=True)
    draw_text(draw, (140, 176), "TRỢ LÝ PHÁP LÝ", 9, "#8bd2c5", bold=True)
    for index, label in enumerate(("Hỏi đáp pháp luật", "Tạo hợp đồng", "Review hợp đồng", "So sánh hợp đồng")):
        y = 245 + index * 56
        if index == 0:
            rounded(draw, (74, y - 13, 258, y + 29), 11, "#f6ead1")
            color = DEEP
        else:
            color = "#b7cfca"
        draw_text(draw, (96, y + 8), label, 13, color, bold=True, anchor="lm")
    draw.line((276, 178, 1224, 178), fill=LINE, width=1)
    draw_text(draw, (316, 147), "Trợ lý pháp lý", 16, INK, bold=True)
    draw_text(draw, (316, 167), "Đối chiếu căn cứ liên quan", 10, MUTED)


def scene_ask(local: float, duration: float, global_progress: float) -> Image.Image:
    image = base_frame(global_progress)
    draw = ImageDraw.Draw(image)
    draw_app_shell(draw)
    draw_text(draw, (750, 245), "Bạn cần hỗ trợ điều gì?", 34, INK, bold=True, serif=True, anchor="mm")
    rounded(draw, (392, 312, 1110, 484), 24, WHITE, "#a9cbc3", 2)
    question = "Người lao động có quyền từ chối công việc nguy hiểm không?"
    typed = question[: int(len(question) * min(1.0, local / 3.2))]
    paragraph(draw, (422, 343), typed, 630, 17, INK, line_gap=8)
    draw.line((414, 426, 1088, 426), fill=LINE, width=1)
    rounded(draw, (416, 440, 452, 476), 18, "#edf4f2", "#c7dcd6")
    draw_text(draw, (434, 458), "+", 24, BRAND, anchor="mm")
    rounded(draw, (1050, 440, 1086, 476), 10, DEEP)
    draw_text(draw, (1068, 458), "→", 18, WHITE, bold=True, anchor="mm")
    if local > 3.5:
        menu_y = 298
        rounded(draw, (405, menu_y, 680, menu_y + 130), 16, PAPER, LINE, 2)
        draw_text(draw, (428, menu_y + 33), "▧", 17, BRAND, bold=True, anchor="lm")
        draw_text(draw, (458, menu_y + 33), "Tải ảnh", 14, INK, bold=True, anchor="lm")
        draw_text(draw, (428, menu_y + 78), "▤", 17, BRAND, bold=True, anchor="lm")
        draw_text(draw, (458, menu_y + 78), "Tải tài liệu", 14, INK, bold=True, anchor="lm")
        draw.line((420, menu_y + 100, 665, menu_y + 100), fill=LINE, width=1)
        draw_text(draw, (428, menu_y + 116), "Hoặc dán ảnh bằng Ctrl + V", 10, MUTED, anchor="lm")
    draw_text(draw, (392, 548), "Mô tả vai trò · sự việc · thời gian · điều bạn muốn biết", 12, BRAND, bold=True)
    return image


def scene_answer(local: float, duration: float, global_progress: float) -> Image.Image:
    image = base_frame(global_progress)
    draw = ImageDraw.Draw(image)
    draw_app_shell(draw)
    rounded(draw, (798, 218, 1136, 278), 17, "#e3f0ec", "#c4dbd5")
    draw_text(draw, (827, 248), "Tôi có thể từ chối công việc nguy hiểm?", 13, INK, anchor="lm")
    rounded(draw, (332, 311, 374, 353), 12, DEEP)
    draw_scale(draw, (353, 332), 23, "#f5ddb0", 3)
    draw_text(draw, (395, 318), "Có. Bạn có quyền từ chối hoặc rời nơi làm việc khi có", 14, INK)
    draw_text(draw, (395, 342), "nguy cơ rõ ràng đe dọa trực tiếp tính mạng, sức khỏe [S1].", 14, INK)
    rounded(draw, (395, 376, 1116, 468), 15, "#f5f3ec", LINE)
    rounded(draw, (414, 394, 450, 430), 10, MINT)
    draw_text(draw, (432, 412), "S1", 10, BRAND, bold=True, anchor="mm")
    draw_text(draw, (466, 398), "Bộ luật Lao động 2019", 14, INK, bold=True)
    draw_text(draw, (466, 424), "Điều 5 · Quyền và nghĩa vụ của người lao động", 11, MUTED)
    rounded(draw, (945, 394, 1095, 436), 21, "#e5f1ed")
    draw_text(draw, (1020, 415), "CÒN HIỆU LỰC", 9, BRAND, bold=True, anchor="mm")
    if local > 3.1:
        highlight = int(3 * math.sin((local - 3.1) * 5))
        rounded(draw, (927 - highlight, 487 - highlight, 1116 + highlight, 535 + highlight), 14, DEEP)
        draw_text(draw, (1021, 511), "Mở văn bản gốc  ↗", 12, WHITE, bold=True, anchor="mm")
    draw_text(draw, (395, 574), "Sao chép      ♡ Hữu ích      ♧ Chưa tốt", 11, MUTED)
    return image


def scene_contracts(local: float, duration: float, global_progress: float) -> Image.Image:
    image = base_frame(global_progress, inverse=True)
    draw = ImageDraw.Draw(image)
    draw_text(draw, (640, 145), "CÔNG CỤ HỢP ĐỒNG", 12, "#70c6b6", bold=True, anchor="mm")
    draw_text(draw, (640, 195), "Chọn đúng luồng cho tài liệu", 41, WHITE, bold=True, serif=True, anchor="mm")
    cards = [
        ("01", "Tạo hợp đồng", "Từ yêu cầu đến bản nháp có cấu trúc."),
        ("02", "Review hợp đồng", "Tìm rủi ro và điều khoản bất lợi."),
        ("03", "So sánh hợp đồng", "Đối chiếu thay đổi giữa hai phiên bản."),
    ]
    for index, (number, title, description) in enumerate(cards):
        delay = index * 0.35
        reveal = smoothstep((local - delay) / 0.75)
        x = 104 + index * 360
        y = 278 + int(34 * (1 - reveal))
        rounded(draw, (x, y, x + 330, y + 254), 21, "#104946", "#28635e", 2)
        rounded(draw, (x + 22, y + 22, x + 68, y + 68), 13, "#1a5a55")
        draw_text(draw, (x + 45, y + 45), number, 11, "#d6b16c", bold=True, anchor="mm")
        draw_text(draw, (x + 22, y + 104), title, 21, WHITE, bold=True)
        paragraph(draw, (x + 22, y + 143), description, 275, 13, "#b9ceca", line_gap=7)
        draw_text(draw, (x + 286, y + 218), "→", 23, "#70c6b6", bold=True, anchor="mm")
    return image


def scene_end(local: float, duration: float, global_progress: float) -> Image.Image:
    image = base_frame(global_progress, inverse=True)
    draw = ImageDraw.Draw(image)
    pulse = 1 + 0.04 * math.sin(local * 5)
    icon_size = round(76 * pulse)
    rounded(draw, (640 - icon_size // 2, 156 - icon_size // 2, 640 + icon_size // 2, 156 + icon_size // 2), 22, "#fffefa")
    draw_scale(draw, (640, 156), round(40 * pulse), DEEP, 4)
    draw_text(draw, (640, 254), "Sẵn sàng hỏi VLegal?", 48, WHITE, bold=True, serif=True, anchor="mm")
    draw_text(draw, (640, 312), "Đăng nhập bằng Google và bắt đầu từ tình huống của bạn.", 19, "#c4d8d4", anchor="mm")
    rounded(draw, (480, 374, 800, 434), 30, "#fffefa")
    rounded(draw, (497, 389, 527, 419), 15, WHITE, "#d4dedb")
    draw_text(draw, (512, 404), "G", 15, "#4285f4", bold=True, anchor="mm")
    draw_text(draw, (551, 404), "Tiếp tục với Google", 15, DEEP, bold=True, anchor="lm")
    draw_text(draw, (640, 502), "vlegalai-201653369723.asia-southeast1.run.app", 12, "#70c6b6", anchor="mm")
    return image


SCENES = [
    (0.0, 4.0, scene_intro),
    (4.0, 9.0, scene_login),
    (9.0, 16.0, scene_ask),
    (16.0, 23.0, scene_answer),
    (23.0, 28.0, scene_contracts),
    (28.0, 30.0, scene_end),
]


def render_frame(time_seconds: float) -> Image.Image:
    global_progress = min(1.0, time_seconds / DURATION_SECONDS)
    for start, end, renderer in SCENES:
        if start <= time_seconds < end or (end == DURATION_SECONDS and time_seconds >= start):
            local = time_seconds - start
            frame = renderer(local, end - start, global_progress)
            alpha = scene_alpha(local, end - start)
            if alpha < 255:
                fallback = base_frame(global_progress, inverse=renderer in {scene_intro, scene_contracts, scene_end})
                return Image.blend(fallback, frame, alpha / 255)
            return frame
    return scene_end(0, 2, global_progress)


def build() -> None:
    PUBLIC.mkdir(parents=True, exist_ok=True)
    poster = render_frame(12.4)
    poster.save(POSTER, quality=90, optimize=True, progressive=True)

    ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg,
        "-y",
        "-f", "rawvideo",
        "-vcodec", "rawvideo",
        "-pix_fmt", "rgb24",
        "-s", f"{WIDTH}x{HEIGHT}",
        "-r", str(FPS),
        "-i", "-",
        "-an",
        "-vcodec", "libx264",
        "-preset", "medium",
        "-crf", "21",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        str(OUTPUT),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for frame_index in range(FPS * DURATION_SECONDS):
            frame = render_frame(frame_index / FPS)
            process.stdin.write(frame.tobytes())
    finally:
        process.stdin.close()
    return_code = process.wait()
    if return_code:
        raise SystemExit(f"ffmpeg exited with code {return_code}")
    print(f"Built {OUTPUT} ({OUTPUT.stat().st_size / 1024 / 1024:.2f} MiB)")
    print(f"Built {POSTER} ({POSTER.stat().st_size / 1024:.1f} KiB)")


if __name__ == "__main__":
    build()
