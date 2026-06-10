import os
import subprocess
import tempfile
from typing import List

import arabic_reshaper
import numpy as np
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFont

from utils.logger import get_logger

log = get_logger(__name__)

THUMBNAIL_DIR = "data/thumbnails"
THUMBNAIL_SIZE = (1280, 720)

_ARABIC_FONT_PATH = "/usr/share/fonts/opentype/fonts-hosny-amiri/Amiri-Bold.ttf"
_FALLBACK_FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

_LINE_FONT_SIZES = [72, 64, 64]
_MAX_LINES = 3
_CHARS_PER_LINE = 20
_TEXT_MARGIN = 40
_LINE_SPACING = 10
_GRADIENT_OPACITY = 0.8


def get_duration(file_path: str) -> float:
    """Return media duration in seconds via ffprobe."""
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        file_path,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def _extract_frame(video_path: str, timestamp: float, output_path: str) -> bool:
    """Extract a single frame at `timestamp` seconds. Returns True on success."""
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(timestamp),
        "-i", video_path,
        "-frames:v", "1",
        "-q:v", "2",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        log.warning("ffmpeg frame extraction failed at %.2fs: %s", timestamp, exc)
        return False
    return os.path.exists(output_path)


_LAPLACIAN_CENTER = -4


def _sharpness_score(image: Image.Image) -> float:
    """Laplacian variance — higher means sharper."""
    gray = np.asarray(image.convert("L"), dtype=np.float64)
    laplacian = (
        gray[1:-1, 1:-1] * _LAPLACIAN_CENTER
        + gray[0:-2, 1:-1]
        + gray[2:, 1:-1]
        + gray[1:-1, 0:-2]
        + gray[1:-1, 2:]
    )
    return float(laplacian.var())


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    try:
        return ImageFont.truetype(_ARABIC_FONT_PATH, size)
    except OSError:
        return ImageFont.truetype(_FALLBACK_FONT_PATH, size)


def _shape_text(text: str) -> str:
    """Reshape + reorder Arabic text for correct rendering."""
    return get_display(arabic_reshaper.reshape(text))


def _wrap_title(title: str) -> List[str]:
    """Split title into at most _MAX_LINES lines of ~_CHARS_PER_LINE chars."""
    words = title.split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or len(candidate) <= _CHARS_PER_LINE:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)

    if len(lines) > _MAX_LINES:
        head = lines[: _MAX_LINES - 1]
        tail = " ".join(lines[_MAX_LINES - 1:])
        lines = head + [tail]

    return lines[:_MAX_LINES]


def _resize_and_crop(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    """Resize to cover `size` while keeping aspect ratio, then center-crop."""
    target_w, target_h = size
    src_w, src_h = image.size

    scale = max(target_w / src_w, target_h / src_h)
    new_w, new_h = round(src_w * scale), round(src_h * scale)
    image = image.resize((new_w, new_h), Image.LANCZOS)

    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    return image.crop((left, top, left + target_w, top + target_h))


def _apply_gradient(image: Image.Image) -> Image.Image:
    """Dark gradient over the bottom 50%: transparent at top → 80% black at bottom."""
    width, height = image.size
    gradient_height = height // 2

    gradient = Image.new("L", (1, gradient_height))
    for y in range(gradient_height):
        alpha = int(255 * _GRADIENT_OPACITY * (y / max(gradient_height - 1, 1)))
        gradient.putpixel((0, y), alpha)
    gradient = gradient.resize((width, gradient_height))

    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    black = Image.new("RGBA", (width, gradient_height), (0, 0, 0, 255))
    black.putalpha(gradient)
    overlay.paste(black, (0, height - gradient_height), black)

    return Image.alpha_composite(image.convert("RGBA"), overlay)


def _draw_title(image: Image.Image, title: str) -> Image.Image:
    """Draw the (Arabic-shaped) title in the bottom 40% of the image, left-aligned."""
    width, height = image.size
    draw = ImageDraw.Draw(image)

    lines = _wrap_title(title)

    rendered = []
    total_height = 0
    for i, line in enumerate(lines):
        font_size = _LINE_FONT_SIZES[min(i, len(_LINE_FONT_SIZES) - 1)]
        font = _load_font(font_size)
        shaped = _shape_text(line)
        bbox = draw.textbbox((0, 0), shaped, font=font, stroke_width=3)
        line_height = bbox[3] - bbox[1]
        rendered.append((shaped, font, line_height))
        total_height += line_height + _LINE_SPACING
    total_height -= _LINE_SPACING

    bottom_zone_top = int(height * 0.6)
    y = max(bottom_zone_top, height - _TEXT_MARGIN - total_height)

    for shaped, font, line_height in rendered:
        draw.text(
            (_TEXT_MARGIN, y),
            shaped,
            font=font,
            fill="white",
            stroke_width=3,
            stroke_fill="black",
        )
        y += line_height + _LINE_SPACING

    return image


def generate(local_path: str, title: str, db_id: int) -> str:
    """Generate a 1280x720 thumbnail for `local_path` and save it as
    data/thumbnails/{db_id}.jpg. Returns the saved path.
    """
    duration = get_duration(local_path)
    timestamps = [duration * 0.2, duration * 0.4, duration * 0.6]

    with tempfile.TemporaryDirectory() as tmpdir:
        candidates = []
        for i, ts in enumerate(timestamps):
            frame_path = os.path.join(tmpdir, f"frame_{i}.jpg")
            if _extract_frame(local_path, ts, frame_path):
                candidates.append(frame_path)

        if not candidates:
            raise RuntimeError(f"No frames could be extracted from {local_path}")

        best_path = max(candidates, key=lambda p: _sharpness_score(Image.open(p)))
        image = Image.open(best_path).convert("RGB")

    image = _resize_and_crop(image, THUMBNAIL_SIZE)
    image = _apply_gradient(image)
    image = _draw_title(image, title)

    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    out_path = os.path.join(THUMBNAIL_DIR, f"{db_id}.jpg")
    image.convert("RGB").save(out_path, "JPEG", quality=90)

    log.info("Generated thumbnail for video %d: %s", db_id, out_path)
    return out_path
