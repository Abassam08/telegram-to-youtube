import os
import subprocess
import urllib.request
from typing import Optional

from PIL import Image, ImageDraw, ImageFont
import arabic_reshaper
from bidi.algorithm import get_display

import config
from utils.logger import get_logger

log = get_logger(__name__)

FONT_URL = "https://raw.githubusercontent.com/Gue3bara/Cairo/master/fonts/ttf/Cairo-Bold.ttf"
FONT_DIR = "data/fonts"
FONT_PATH = os.path.join(FONT_DIR, "Cairo-Bold.ttf")


def _ensure_font_exists() -> None:
    if not os.path.exists(FONT_PATH):
        os.makedirs(FONT_DIR, exist_ok=True)
        log.info("Downloading Cairo font for CTA overlay...")
        try:
            urllib.request.urlretrieve(FONT_URL, FONT_PATH)
            log.info("Font downloaded successfully to %s", FONT_PATH)
        except Exception as exc:
            log.error("Failed to download font: %s", exc)


def _check_ffmpeg() -> bool:
    try:
        subprocess.run(
            ["ffmpeg", "-version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _create_cta_image(text: str, output_path: str) -> None:
    """Generates a transparent PNG with the Arabic text safely shaped and rendered."""
    _ensure_font_exists()

    # Prepare Arabic text
    reshaped_text = arabic_reshaper.reshape(text)
    bidi_text = get_display(reshaped_text)

    try:
        font = ImageFont.truetype(FONT_PATH, 40)  # Smaller font size
    except IOError:
        log.error("Could not load font from %s, falling back to default.", FONT_PATH)
        font = ImageFont.load_default()

    # Create a dummy image to calculate text dimensions
    dummy_img = Image.new("RGBA", (1, 1), (255, 255, 255, 0))
    dummy_draw = ImageDraw.Draw(dummy_img)
    
    # Calculate bounding box
    bbox = dummy_draw.textbbox((0, 0), bidi_text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Add padding for background
    padding_x = 40
    padding_y = 20
    img_width = text_width + (padding_x * 2)
    img_height = text_height + (padding_y * 2)

    # Create actual image with transparent background
    img = Image.new("RGBA", (img_width, img_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Draw semi-transparent black background rectangle with rounded corners
    rect_coords = [0, 0, img_width, img_height]
    draw.rounded_rectangle(rect_coords, radius=15, fill=(0, 0, 0, 160))

    # Draw text in white
    text_x = padding_x - bbox[0]
    text_y = padding_y - bbox[1]
    draw.text((text_x, text_y), bidi_text, font=font, fill=(255, 255, 255, 255))

    img.save(output_path)


def _get_video_duration(video_path: str) -> float:
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries",
            "format=duration", "-of",
            "default=noprint_wrappers=1:nokey=1", video_path
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        return float(result.stdout.strip())
    except Exception as exc:
        log.error("Failed to get video duration: %s", exc)
        return 0.0

def add_cta_overlay(video_path: str, cta_text: str = "اشترك للمزيد") -> str:
    """
    Overlays a CTA on the video if ffmpeg is available.
    Returns the video_path. Modifies the file in-place (conceptually).
    """
    if not os.path.exists(video_path):
        return video_path

    if not _check_ffmpeg():
        log.warning("ffmpeg is not installed or not in PATH. Skipping CTA overlay.")
        return video_path

    png_path = os.path.join(config.TEMP_DOWNLOAD_DIR, "cta_overlay.png")
    temp_output_path = video_path + ".temp.mp4"

    try:
        _create_cta_image(cta_text, png_path)

        duration = _get_video_duration(video_path)
        start_time = duration * 0.7 if duration > 0 else 0

        # ffmpeg command to overlay the image at top right corner (W-w-30, 30)
        # and only show it for the last 30% of the video
        overlay_filter = f"[0:v][1:v]overlay=W-w-30:30:enable='between(t,{start_time},{duration})'"

        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", png_path,
            "-filter_complex", overlay_filter,
            "-c:a", "copy",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            temp_output_path
        ]

        log.info("Applying CTA overlay to %s...", os.path.basename(video_path))
        subprocess.run(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True
        )

        # Replace original video with processed video
        os.remove(video_path)
        os.rename(temp_output_path, video_path)
        log.info("CTA overlay applied successfully.")

    except subprocess.CalledProcessError as exc:
        log.error("ffmpeg failed to process video: %s", exc.stderr.decode('utf-8', errors='ignore'))
        if os.path.exists(temp_output_path):
            os.remove(temp_output_path)
    except Exception as exc:
        log.error("Failed to apply CTA overlay: %s", exc)
        if os.path.exists(temp_output_path):
            os.remove(temp_output_path)
    finally:
        if os.path.exists(png_path):
            os.remove(png_path)

    return video_path
