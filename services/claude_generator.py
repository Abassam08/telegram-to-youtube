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


FOLLOW_LINE = "تابعونا للمزيد من المحتوى المسيحي ✝️"


def _merge_tags(dynamic: List[str]) -> List[str]:
    """Fixed tags first, then dynamic — deduplicated, order preserved."""
    seen: dict[str, None] = {}
    for tag in config.YOUTUBE_FIXED_TAGS + dynamic:
        seen[tag] = None
    return list(seen)


def _merge_hashtags(dynamic: List[str]) -> List[str]:
    """Fixed hashtags first, then 1-2 dynamic ones — deduplicated."""
    seen: dict[str, None] = {}
    for tag in config.YOUTUBE_FIXED_HASHTAGS + dynamic:
        seen[tag] = None
    return list(seen)


def generate_metadata(
    caption: str,
    filename: str,
    date: Optional[str] = None,
) -> Dict[str, object]:
    """Call Gemini to produce Arabic title, description, tags, and hashtags.

    Args:
        caption:  Telegram video caption (Arabic text).
        filename: Original video filename.
        date:     Post date string (e.g. "2026-05-24"), used as context.

    Returns:
        {
            'title':       str,           # clean title, no hashtags
            'description': str,           # 2-3 sentences + follow line, no hashtags
            'tags':        list[str],     # FIXED_TAGS + dynamic tags
            'hashtags':    list[str],     # FIXED_HASHTAGS + 1-2 dynamic hashtags
        }
        Hashtag placement (Shorts vs regular) is handled by the uploader.
    """
    date_line = f"Post date: {date}" if date else ""

    prompt = f"""You are managing an Arabic Christian YouTube channel.

Given the video information below, generate:
1. A compelling Arabic YouTube title (max 80 characters, NO hashtags in the title)
2. An Arabic YouTube description: 2-3 sentences summarising the video (NO hashtags)
3. A list of 5–8 dynamic Arabic tags specific to this video's content
4. A list of 1-2 Arabic hashtags (with # prefix) relevant to the specific content — do NOT include #مسيحي, #يسوع, or #الكنيسة as those are added automatically

Video filename: {filename}
{date_line}
Video caption: {caption or "Not provided"}

Respond ONLY with valid JSON — no markdown fences, no explanation:
{{
  "title": "العنوان هنا",
  "description": "وصف الفيديو هنا.",
  "tags": ["وسم1", "وسم2"],
  "hashtags": ["#موضوع1", "#موضوع2"]
}}

Rules:
- Everything must be in Arabic
- Title must be clean — no hashtags, max 80 characters
- Description must be 2-3 sentences only, no hashtags, no bullet points
- Tags are plain keywords (no # prefix)
- Hashtags field: only 1-2 niche content-specific hashtags with # prefix"""

    try:
        response = _get_client().models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
        )
        raw = response.text.strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(raw)

        title = str(data.get("title") or filename)

        description = str(data.get("description") or "")
        if description and not description.endswith(FOLLOW_LINE):
            description = description.rstrip() + "\n" + FOLLOW_LINE

        dynamic_tags: List[str] = data.get("tags") or []
        if not isinstance(dynamic_tags, list):
            dynamic_tags = []
        dynamic_tags = [t for t in dynamic_tags if isinstance(t, str)]

        dynamic_hashtags: List[str] = data.get("hashtags") or []
        if not isinstance(dynamic_hashtags, list):
            dynamic_hashtags = []
        # ensure # prefix and strip any that duplicate fixed hashtags
        dynamic_hashtags = [
            h if h.startswith("#") else f"#{h}"
            for h in dynamic_hashtags
            if isinstance(h, str)
        ]

        tags     = _merge_tags(dynamic_tags)
        hashtags = _merge_hashtags(dynamic_hashtags)

        log.info(
            "Gemini — title: %s | tags: %d | hashtags: %s",
            title, len(tags), " ".join(hashtags),
        )
        return {
            "title":       title,
            "description": description,
            "tags":        tags,
            "hashtags":    hashtags,
        }

    except (json.JSONDecodeError, KeyError, IndexError) as exc:
        log.warning("Gemini metadata parse failed (%s), using filename fallback", exc)
    except Exception as exc:
        log.error("Gemini API error: %s", exc)

    fallback_title = filename.rsplit(".", 1)[0].replace("_", " ")
    return {
        "title":       fallback_title,
        "description": FOLLOW_LINE,
        "tags":        list(config.YOUTUBE_FIXED_TAGS),
        "hashtags":    list(config.YOUTUBE_FIXED_HASHTAGS),
    }
