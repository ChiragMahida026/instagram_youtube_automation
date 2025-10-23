import os
import subprocess
from pathlib import Path

import pytest

from instauto.downloader import _collect_posts, download_posts


def test_collect_posts(tmp_path):
    """Ensure that _collect_posts groups media files and reads captions."""
    profile_dir = tmp_path / "user"
    profile_dir.mkdir()
    # Create a caption file and two media files sharing the same prefix
    caption_path = profile_dir / "2025-10-10_12-00-00_UTC.txt"
    caption_path.write_text("Test caption with #hashtag", encoding="utf-8")
    # Create associated media files
    (profile_dir / "2025-10-10_12-00-00_UTC.jpg").write_bytes(b"image content")
    (profile_dir / "2025-10-10_12-00-00_UTC_2.mp4").write_bytes(b"video content")

    posts = _collect_posts(profile_dir)
    assert len(posts) == 1
    post = posts[0]
    assert post.base_name == "2025-10-10_12-00-00_UTC"
    # Both media files should be grouped
    assert len(post.media_files) == 2
    assert post.caption == "Test caption with #hashtag"
    # Timestamp should parse correctly
    assert post.timestamp.year == 2025
    assert post.timestamp.hour == 12


def test_download_posts_invokes_instaloader(monkeypatch, tmp_path):
    """download_posts should invoke the instaloader CLI and collect posts."""
    # Prepare a fake run that populates the expected output directory
    calls = []

    def fake_run(cmd, check=True):
        # record call
        calls.append(cmd)
        # simulate instaloader output: create profile directory and files
        profile_dir = tmp_path / "downloads" / "user"
        profile_dir.mkdir(parents=True, exist_ok=True)
        # create dummy caption and media files
        cap = profile_dir / "2025-01-01_00-00-00_UTC.txt"
        cap.write_text("Caption", encoding="utf-8")
        (profile_dir / "2025-01-01_00-00-00_UTC.mp4").write_bytes(b"video")
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    # call download_posts
    posts = download_posts(
        "user", download_all=True, output_dir=tmp_path / "downloads", extra_args=[]
    )
    # ensure CLI was invoked with instaloader
    assert calls, "instaloader CLI was not invoked"
    assert calls[0][0] == "instaloader"
    # ensure posts were collected
    assert len(posts) == 1
    assert posts[0].caption == "Caption"