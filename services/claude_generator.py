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


_IDENTITY_LINE = (
    "قناة متخصصة في حوارات معاذ عليان ومحمود داود ومقارنة الأديان والحوار الإسلامي المسيحي"
)

_SEO_FOOTER = (
    "---\n"
    "معاذ عليان | محمود داود | حوار إسلامي مسيحي\n"
    "مقارنة أديان | الرد على الشبهات | moaz alian\n"
    "mahmoud dawood | islamic christian debate\n"
    "حوارات مفتوحة | مناظرات إسلامية مسيحية"
)

_P1_TAGS = [
    "معاذ عليان", "محمود داود", "moaz alian",
    "mahmoud dawood", "حوار إسلامي مسيحي", "مقارنة أديان",
]

_P3_TAGS = [
    "الرد على الشبهات", "حوارات مفتوحة",
    "islamic christian debate", "مناظرات دينية",
]


def _merge_hashtags(dynamic: List[str]) -> List[str]:
    """Fixed hashtags first, then 1-2 dynamic ones — deduplicated, order preserved."""
    seen: dict[str, None] = {}
    for tag in config.YOUTUBE_FIXED_HASHTAGS + dynamic:
        seen[tag] = None
    return list(seen)


def _build_tags(dynamic: List[str]) -> List[str]:
    """P1 (6 hardcoded) + P2 (up to 5 dynamic) + P3 (4 hardcoded), trimmed to ≤490 chars."""
    p2 = dynamic[:5]
    tags = list(_P1_TAGS) + p2 + list(_P3_TAGS)
    min_len = len(_P1_TAGS) + len(p2)
    while len(", ".join(tags)) > 490 and len(tags) > min_len:
        tags.pop()
    return tags


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
            'description': str,           # structured description with fixed SEO sections
            'tags':        list[str],     # P1 (6) + 5 dynamic + P3 (4) = 15 tags
            'hashtags':    list[str],     # FIXED_HASHTAGS + 1-2 dynamic hashtags
        }
        Hashtag placement (Shorts vs regular) is handled by the uploader.
    """
    date_line = f"Post date: {date}" if date else ""

    prompt = f"""You are managing an Arabic YouTube channel featuring Islamic-Christian dialogue between معاذ عليان and محمود داود.

Given the video information below, generate:
1. A compelling Arabic YouTube title (max 80 characters, NO hashtags in the title)
2. A "description_opener": 1-2 natural Arabic sentences for the opening lines of the description. Must mention "معاذ عليان" and "محمود داود" and the main topic. Example style: "حوار مثير بين معاذ عليان ومحمود داود حول [الموضوع]"
3. A "description_summary": 2-3 natural Arabic sentences summarizing the specific content of this video
4. A list of exactly 5 topic-specific Arabic keywords relevant to this video's content — do NOT include any of these already-fixed tags: معاذ عليان، محمود داود، moaz alian، mahmoud dawood، حوار إسلامي مسيحي، مقارنة أديان، الرد على الشبهات، حوارات مفتوحة، islamic christian debate، مناظرات دينية
5. A list of 1-2 niche content-specific Arabic hashtags (with # prefix)

Video filename: {filename}
{date_line}
Video caption: {caption or "Not provided"}

Respond ONLY with valid JSON — no markdown fences, no explanation:
{{
  "title": "العنوان هنا",
  "description_opener": "السطر الأول والثاني هنا",
  "description_summary": "ملخص الفيديو هنا",
  "tags": ["وسم1", "وسم2", "وسم3", "وسم4", "وسم5"],
  "hashtags": ["#موضوع1", "#موضوع2"]
}}

Rules:
- Title: clean Arabic, no hashtags, max 80 characters
- description_opener: naturally includes names معاذ عليان and محمود داود and the main topic
- description_summary: 2-3 sentences specific to this video's content, no hashtags, no bullet points
- tags: exactly 5 plain Arabic keywords (no # prefix), specific to this video's topic
- hashtags: 1-2 niche content-specific hashtags with # prefix, do NOT include #مسيحي, #يسوع, or #الكنيسة"""

    try:
        response = _get_client().models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
        )
        raw = response.text.strip()

        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

        data = json.loads(raw)

        # ── Title — DO NOT MODIFY THIS LOGIC ──────────────────────────────────
        title = str(data.get("title") or filename)

        # ── Description — structured assembly ─────────────────────────────────
        opener  = str(data.get("description_opener") or "").strip()
        summary = str(data.get("description_summary") or "").strip()
        description = (
            opener + "\n"
            + _IDENTITY_LINE + "\n\n"
            + summary + "\n\n"
            + _SEO_FOOTER
        )

        # ── Tags — P1 + 5 dynamic + P3, trimmed if joined length > 490 chars ──
        dynamic_tags: List[str] = data.get("tags") or []
        if not isinstance(dynamic_tags, list):
            dynamic_tags = []
        dynamic_tags = [t for t in dynamic_tags if isinstance(t, str)]
        tags = _build_tags(dynamic_tags)

        # ── Hashtags — unchanged logic ─────────────────────────────────────────
        dynamic_hashtags: List[str] = data.get("hashtags") or []
        if not isinstance(dynamic_hashtags, list):
            dynamic_hashtags = []
        dynamic_hashtags = [
            h if h.startswith("#") else f"#{h}"
            for h in dynamic_hashtags
            if isinstance(h, str)
        ]
        hashtags = _merge_hashtags(dynamic_hashtags)

        log.info(
            "Gemini — title: %s | tags (%d, %d chars): %s",
            title, len(tags), len(", ".join(tags)), tags,
        )
        log.info("Sample description:\n%s", description)

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
    fallback_description = _IDENTITY_LINE + "\n\n" + _SEO_FOOTER
    return {
        "title":       fallback_title,
        "description": fallback_description,
        "tags":        list(_P1_TAGS + _P3_TAGS),
        "hashtags":    list(config.YOUTUBE_FIXED_HASHTAGS),
    }
