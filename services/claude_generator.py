import json
from typing import Dict, List, Optional

from google import genai

import config
from utils.logger import get_logger

log = get_logger(__name__)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


def _merge_tags(dynamic: List[str]) -> List[str]:
    """Fixed tags first, then dynamic — deduplicated, order preserved."""
    seen: dict[str, None] = {}
    for tag in config.YOUTUBE_FIXED_TAGS + dynamic:
        seen[tag] = None
    return list(seen)


FOLLOW_LINE = "تابعونا للمزيد من المحتوى المسيحي ✝️"


def generate_metadata(
    caption: str,
    filename: str,
    date: Optional[str] = None,
) -> Dict[str, object]:
    """Call Gemini to produce an Arabic title, description, and dynamic tags.

    Args:
        caption:  Telegram video caption (Arabic text).
        filename: Original video filename.
        date:     Post date string (e.g. "2026-05-24"), used as context.

    Returns:
        {'title': str, 'description': str, 'tags': list[str]}
        Tags = YOUTUBE_FIXED_TAGS + dynamic tags (no duplicates).
        Description is 2-3 Arabic sentences ending with the channel follow line.
    """
    date_line = f"Post date: {date}" if date else ""

    prompt = f"""You are managing an Arabic Christian YouTube channel.

Given the video information below, generate:
1. A compelling Arabic YouTube title (max 100 characters) based on the caption content
2. An Arabic YouTube description: 2-3 sentences summarising the video content
3. A list of 5–8 dynamic Arabic tags specific to this video's content

Video filename: {filename}
{date_line}
Video caption: {caption or "Not provided"}

Respond ONLY with valid JSON — no markdown fences, no explanation:
{{
  "title": "العنوان هنا",
  "description": "وصف الفيديو هنا.",
  "tags": ["وسم1", "وسم2", "وسم3"]
}}

Rules:
- Title, description, and tags must all be in Arabic
- Base everything on the actual caption content, not generic phrases
- Title should be engaging and SEO-friendly
- Description must be 2-3 sentences only — no bullet points, no hashtags
- Tags must be specific keywords from the caption (topics, names, themes)"""

    try:
        response = _get_client().models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
        )
        raw = response.text.strip()

        # strip markdown code fences if Gemini wraps the JSON
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(raw)

        title = str(data.get("title") or filename)

        description = str(data.get("description") or "")
        if description and not description.endswith(FOLLOW_LINE):
            description = description.rstrip() + "\n" + FOLLOW_LINE

        dynamic: List[str] = data.get("tags") or []
        if not isinstance(dynamic, list):
            dynamic = []
        dynamic = [t for t in dynamic if isinstance(t, str)]

        tags = _merge_tags(dynamic)
        log.info(
            "Gemini generated title: %s  (%d fixed + %d dynamic = %d tags)",
            title, len(config.YOUTUBE_FIXED_TAGS), len(dynamic), len(tags),
        )
        return {"title": title, "description": description, "tags": tags}

    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        log.warning("Gemini metadata parse failed (%s), using filename fallback", exc)
    except Exception as exc:
        log.error("Gemini API error: %s", exc)

    fallback_title = filename.rsplit(".", 1)[0].replace("_", " ")
    return {
        "title":       fallback_title,
        "description": FOLLOW_LINE,
        "tags":        list(config.YOUTUBE_FIXED_TAGS),
    }
