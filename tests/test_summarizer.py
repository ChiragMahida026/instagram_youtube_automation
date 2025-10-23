from instauto.summarizer import (
    generate_title_description,
    _heuristic_title_description,
    _clean_caption,
    _extract_first_sentence,
)


def test_heuristic_removes_hashtags():
    caption = "Never give up on your dreams! #motivation #inspiration"
    title, description = _heuristic_title_description(caption)
    # Title should not include hashtags
    assert "#" not in title
    assert title.startswith("Never give up on your dreams")
    # Description should be unchanged except whitespace
    assert description == "Never give up on your dreams! #motivation #inspiration"


def test_extract_first_sentence():
    text = "Hello world. Second sentence!"  # first sentence ends at period
    first = _extract_first_sentence(text)
    assert first == "Hello world."


def test_generate_title_description_simple():
    caption = "Just another day at the park. Enjoying the sun."
    title, description = generate_title_description(caption, use_chatgpt=False)
    assert title.startswith("Just another day at the park")
    assert description == caption


def test_generate_title_description_chatgpt_fallback(monkeypatch):
    """If ChatGPT fails or returns None the function should fall back."""

    # Force _chatgpt_summary to return None
    from instauto import summarizer as mod

    monkeypatch.setattr(mod, "_chatgpt_summary", lambda caption: None)
    caption = "Testing fallback when ChatGPT is unavailable."
    title, description = generate_title_description(caption, use_chatgpt=True)
    assert title.startswith("Testing fallback when ChatGPT")