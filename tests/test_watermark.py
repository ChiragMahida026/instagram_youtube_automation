"""Tests for the watermark utility.

This module exercises the watermark helper functions.  We avoid actually
rendering videos since that would require moviepy and ffmpeg; instead
we test argument validation and helper functions.  To test full
rendering, run a manual integration test with a sample video and
watermark image.
"""
import builtins
from pathlib import Path
import pytest

from instauto.watermark import _get_position_offsets, apply_watermark


def test_get_position_offsets_basic():
    vid_size = (1000, 500)
    wm_size = (200, 100)
    # bottom-right default
    x, y = _get_position_offsets(vid_size, wm_size, "bottom-right", margin=10)
    assert x == 1000 - 200 - 10
    assert y == 500 - 100 - 10
    # top-left
    assert _get_position_offsets(vid_size, wm_size, "top-left", margin=5) == (5, 5)
    # top-right
    assert _get_position_offsets(vid_size, wm_size, "top-right", margin=5) == (1000 - 200 - 5, 5)
    # bottom-left
    assert _get_position_offsets(vid_size, wm_size, "bottom-left", margin=5) == (5, 500 - 100 - 5)


def test_apply_watermark_missing_file(tmp_path: Path):
    # create dummy watermark file
    wm = tmp_path / "wm.png"
    wm.write_bytes(b"")
    # call with missing video
    missing_video = tmp_path / "missing.mp4"
    with pytest.raises(FileNotFoundError):
        apply_watermark(
            video_path=missing_video,
            watermark_image=wm,
            output_path=tmp_path / "out.mp4",
        )