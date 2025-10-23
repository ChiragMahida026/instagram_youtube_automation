import types
from pathlib import Path

import pytest

from instauto.youtube_uploader import upload_video


class FakeStatus:
    def __init__(self, progress):
        self._progress = progress

    def progress(self):
        return self._progress


class FakeRequest:
    def __init__(self):
        self.calls = 0

    def next_chunk(self):
        # Simulate two chunks: first returns status but no response, second returns response
        if self.calls == 0:
            self.calls += 1
            return FakeStatus(0.5), None
        else:
            return None, {"id": "VIDEOID"}


class FakeVideos:
    def insert(self, part, body, media_body):
        # media_body is ignored in this fake
        return FakeRequest()


class FakeService:
    def videos(self):
        return FakeVideos()


def test_upload_video_success(monkeypatch, tmp_path):
    """upload_video should return the video ID when the API call succeeds."""
    # Create a temporary fake video file
    video_file = tmp_path / "test.mp4"
    video_file.write_bytes(b"fake video content")

    # Patch MediaFileUpload to avoid file type checking
    import instauto.youtube_uploader as uploader

    class DummyMedia:
        def __init__(self, path, chunksize=-1, resumable=True):
            self.path = path

    monkeypatch.setattr(uploader, "MediaFileUpload", DummyMedia)

    # Call upload_video with a FakeService instance
    video_id = upload_video(
        video_path=video_file,
        title="Test",
        description="Test description",
        tags=["test"],
        category_id="22",
        privacy_status="unlisted",
        service=FakeService(),
    )
    assert video_id == "VIDEOID"