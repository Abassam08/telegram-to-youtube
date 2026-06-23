"""Generate SEO-optimized YouTube metadata (title, description, tags, hashtags)
from a Whisper transcript, using Gemini.

Tuned for a da'wah channel: introducing Islam in English to a non-Muslim,
non-Arabic-speaking audience.
"""
import json
import os

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GOOGLE_GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-lite-latest")

_client = None


def _get_client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise RuntimeError(
                "GOOGLE_GEMINI_API_KEY is not set. Add it to a .env file "
                "in whisper-playground/ or the repo root."
            )
        from google import genai
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


_PROMPT_TEMPLATE = """You are the social media manager for an English-language YouTube channel \
that introduces Islam to non-Muslim, non-Arabic-speaking viewers. The tone is warm, respectful, \
clear, and non-preachy — aimed at curious newcomers, not an already-Muslim audience.

Below is the auto-transcribed text of a video. Based on it, generate YouTube upload metadata \
optimized for SEO and discoverability (think: what a curious non-Muslim would actually search for).

Transcript:
\"\"\"
{transcript}
\"\"\"

Respond ONLY with valid JSON — no markdown fences, no explanation:
{{
  "title": "...",
  "description": "...",
  "tags": ["...", "..."],
  "hashtags": ["#...", "#..."]
}}

Rules:
- title: max 70 characters, includes a strong searchable keyword (e.g. "Islam", "Quran", "Science"), \
no clickbait lies, no emojis, no hashtags
- description: 3-4 short paragraphs — (1) a 1-2 sentence hook summarizing the video, (2) 2-3 sentences \
expanding on the content/key points, (3) a soft call-to-action inviting viewers to subscribe/comment/learn \
more, (4) a line of relevant hashtags. Written for a non-Muslim audience, plain English, no Arabic unless \
quoting a term that's then explained.
- tags: 12-15 plain-text SEO keywords/phrases relevant to this specific video's content (comma-style list), \
mixing broad (e.g. "Islam for beginners", "Quran science") and specific terms drawn from the transcript
- hashtags: 4-6 hashtags with # prefix, relevant to the video content, popular/discoverable on YouTube
"""


def generate_seo_metadata(transcript: str) -> dict:
    """Call Gemini to produce an English title, description, tags, and hashtags
    for a da'wah-channel video, given its Whisper transcript text.

    Returns:
        {"title": str, "description": str, "tags": list[str], "hashtags": list[str]}
    """
    prompt = _PROMPT_TEMPLATE.format(transcript=transcript.strip())

    response = _get_client().models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
    )
    raw = response.text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    data = json.loads(raw)

    tags = [t for t in (data.get("tags") or []) if isinstance(t, str)]
    hashtags = [
        h if h.startswith("#") else f"#{h}"
        for h in (data.get("hashtags") or [])
        if isinstance(h, str)
    ]

    return {
        "title": str(data.get("title") or "").strip(),
        "description": str(data.get("description") or "").strip(),
        "tags": tags,
        "hashtags": hashtags,
    }


def format_metadata(metadata: dict) -> str:
    """Render metadata dict as a readable block for terminal/file output."""
    lines = [
        "=== Suggested YouTube Metadata ===",
        "",
        "Title:",
        metadata["title"],
        "",
        "Description:",
        metadata["description"],
        "",
        "Tags:",
        ", ".join(metadata["tags"]),
        "",
        "Hashtags:",
        " ".join(metadata["hashtags"]),
    ]
    return "\n".join(lines)
