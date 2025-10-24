"""Utilities for generating YouTube titles and descriptions from Instagram captions.

The default strategy mirrors common guidance: use the Instagram caption as the
basis for your YouTube title and description. Short, descriptive captions make
excellent titles; long captions are truncated for the title and included in
full in the description. Optionally, you can enable ChatGPT-powered
summarisation by setting an environment variable ``OPENAI_API_KEY`` and passing
``use_chatgpt=True``.

The summarisation uses the OpenAI API to generate a concise title and
description. This requires network access and may incur costs depending on
your OpenAI plan. If the API key is missing or a call fails, the function
falls back to the simple heuristic.
"""

from __future__ import annotations

import os
import re
from typing import Tuple, Optional

try:
    import openai  # type: ignore
except ImportError:
    openai = None  # pragma: no cover


def _clean_caption(caption: str) -> str:
    """Remove trailing whitespace and collapse multiple spaces.

    Also strips any leading/trailing newlines.
    """
    return re.sub(r"\s+", " ", caption.strip())


def _extract_first_sentence(text: str) -> str:
    """Extract the first sentence of the caption.

    Splits on punctuation marks such as ".", "!", "?". If no sentence end is
    found returns the entire text. Hashtags (#) are removed because they reduce
    readability in a YouTube title.
    """
    # remove hashtags entirely
    text_no_tags = re.sub(r"#[\w\d_]+", "", text)
    # split on sentence terminators
    for end in [".", "!", "?"]:
        idx = text_no_tags.find(end)
        if idx != -1:
            return text_no_tags[: idx + 1].strip()
    return text_no_tags.strip()


def _heuristic_title_description(caption: str) -> Tuple[str, str]:
    """Derive a YouTube title and description from an Instagram caption.

    If the caption is short (<=80 characters), the entire caption (minus
    hashtags) becomes the title. For longer captions the title is the first
    sentence (sans hashtags) truncated to 80 characters. The full caption is
    used as the description.
    """
    clean = _clean_caption(caption)
    if not clean:
        return "", ""
    first_sentence = _extract_first_sentence(clean)
    # Title: limit to 80 characters to satisfy YouTube guidelines
    title = first_sentence[:80].strip()
    description = clean
    return title, description


def _chatgpt_summary(caption: str) -> Optional[Tuple[str, str]]:
    """Generate title and description using the OpenAI ChatCompletion API.

    Returns None if the API cannot be called or if an error occurs. The
    function instructs GPT to write a five- to ten-word title and a one- to
    two-sentence description summarising the caption. Hashtags are allowed in
    the description but not in the title.
    """
    if openai is None:
        return None  # openai library not installed
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    # configure client
    openai.api_key = api_key
    try:
        prompt = (
            "You are an assistant that turns Instagram captions into YouTube metadata.\n"
            "Given the following caption, produce a short title (5-10 words) with no hashtags,"
            " and a 1-2 sentence description capturing the essence of the post. Keep emojis and hashtags only"
            " in the description.\n\n"
            f"Caption:\n{caption}\n\n"
            "Respond in JSON with keys 'title' and 'description'."
        )
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=200,
        )
        content = response.choices[0].message.content  # type: ignore[index]
        # parse naive JSON output (not robust but sufficient for our usage)
        import json

        data = json.loads(content)
        return data.get("title", ""), data.get("description", "")
    except Exception:
        return None


def generate_title_description(caption: str, use_chatgpt: bool = False) -> Tuple[str, str]:
    """Generate a YouTube title and description from an Instagram caption.

    Parameters
    ----------
    caption: str
        The caption text downloaded from Instagram.
    use_chatgpt: bool
        If True and the ``OPENAI_API_KEY`` environment variable is set, the
        function will attempt to use ChatGPT to summarise the caption. If
        ChatGPT summarisation fails for any reason, the function falls back to
        the heuristic method.

    Returns
    -------
    (title, description)
        The generated title and description strings. These may be empty if the
        input caption is empty.
    """
    caption = caption or ""
    if use_chatgpt:
        summary = _chatgpt_summary(caption)
        if summary:
            return summary
    return _heuristic_title_description(caption)

