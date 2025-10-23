from pathlib import Path
import json

import pytest

from instauto.downloader import PostInfo
from instauto import summarizer
from main import extract_hashtags, process_profile


def test_extract_hashtags():
    text = "Here is a #test caption with multiple #tags and #123numbers"
    tags = extract_hashtags(text)
    assert tags == ["test", "tags", "123numbers"]


def test_process_profile_creates_metadata(monkeypatch, tmp_path):
    """Ensure process_profile writes a metadata file without uploading."""
    # Prepare a fake download_posts to return one post with a video file
    post = PostInfo(
        base_name="2025-01-01_00-00-00_UTC",
        media_files=[tmp_path / "vid.mp4"],
        caption="Caption for testing",
        timestamp=None,
    )
    (tmp_path / "vid.mp4").write_bytes(b"video content")

    monkeypatch.setattr(
        "instauto.downloader.download_posts",
        lambda username, download_all, output_dir: [post],
    )
    # Monkeypatch summariser to deterministic output
    monkeypatch.setattr(
        summarizer,
        "generate_title_description",
        lambda caption, use_chatgpt: ("Title", "Description"),
    )
    # Monkeypatch upload_video to avoid calling YouTube
    monkeypatch.setattr(
        "instauto.youtube_uploader.upload_video", lambda **kwargs: "video123"
    )
    monkeypatch.setattr(
        "instauto.youtube_uploader.get_authenticated_service",
        lambda *args, **kwargs: object(),
    )
    # Run process_profile
    output_dir = tmp_path / "downloads"
    process_profile(
        username="user",
        download_all=False,
        output_dir=output_dir,
        upload_videos=False,
        use_chatgpt=False,
        service_params={},
    )
    # Check metadata file exists and has expected keys
    meta_path = output_dir / "user" / f"{post.base_name}_meta.json"
    assert meta_path.exists()
    meta = json.loads(meta_path.read_text())
    assert meta["title"] == "Title"
    assert meta["description"] == "Description"
    assert meta["uploaded"] is False