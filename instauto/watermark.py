"""Utilities for overlaying a watermark on video files.

This module provides a function to apply a watermark (image) onto a video.
It uses MoviePy under the hood, which is a pure-Python wrapper around
FFmpeg. If MoviePy is not installed or FFmpeg is missing, watermarking
will raise an exception. The caller should handle exceptions gracefully.

Example usage::

    from pathlib import Path
    from instauto.watermark import apply_watermark

    in_file = Path("video.mp4")
    wm_img = Path("logo.png")
    out_file = Path("video_watermarked.mp4")
    apply_watermark(
        video_path=in_file,
        watermark_image=wm_img,
        output_path=out_file,
        position="bottom-right",
        opacity=0.6,
        scale=0.15,
    )

Parameters
----------
video_path : Path
    Path to the input video file.
watermark_image : Path
    Path to the PNG image used as watermark. Transparent backgrounds
    are respected.
output_path : Path
    Path where the watermarked video will be written. The file will be
    overwritten if it exists.
position : str, optional
    Where to place the watermark. Options: "top-left", "top-right",
    "bottom-left", "bottom-right". Defaults to "bottom-right".
opacity : float, optional
    Opacity of the watermark from 0 (fully transparent) to 1 (fully
    opaque). Defaults to 0.5.
scale : float, optional
    Relative scale of the watermark compared to the video width. For
    example, 0.1 makes the watermark width equal to 10% of the video
    width. Defaults to 0.1.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Tuple


def _get_position_offsets(
    video_size: Tuple[int, int],
    wm_size: Tuple[int, int],
    position: str,
    margin: int = 10,
) -> Tuple[int, int]:
    """Compute pixel offsets for the watermark based on desired position.

    Parameters
    ----------
    video_size : Tuple[int, int]
        (width, height) of the video.
    wm_size : Tuple[int, int]
        (width, height) of the watermark.
    position : str
        One of "top-left", "top-right", "bottom-left", "bottom-right".
    margin : int, optional
        Margin in pixels from the edges. Defaults to 10.

    Returns
    -------
    Tuple[int, int]
        (x, y) offset where the watermark's top-left corner should be placed.
    """
    vid_w, vid_h = video_size
    wm_w, wm_h = wm_size
    pos = position.lower()
    if pos == "top-left":
        return (margin, margin)
    if pos == "top-right":
        return (vid_w - wm_w - margin, margin)
    if pos == "bottom-left":
        return (margin, vid_h - wm_h - margin)
    if pos == "bottom-right":
        return (vid_w - wm_w - margin, vid_h - wm_h - margin)
    # default to bottom-right if invalid
    return (vid_w - wm_w - margin, vid_h - wm_h - margin)


def apply_watermark(
    video_path: Path,
    watermark_image: Path,
    output_path: Path,
    *,
    position: str = "bottom-right",
    opacity: float = 0.5,
    scale: float = 0.1,
) -> None:
    """Overlay a watermark image onto a video file.

    This function reads the input video and watermark image, rescales
    the watermark relative to the video size, sets its opacity and
    positions it, then renders a new video to ``output_path``.

    Parameters
    ----------
    video_path : Path
        Input video file.
    watermark_image : Path
        Input watermark PNG.
    output_path : Path
        Destination for watermarked video.
    position : str, optional
        Placement of the watermark: "top-left", "top-right",
        "bottom-left", or "bottom-right". Defaults to
        "bottom-right".
    opacity : float, optional
        Opacity of watermark (0 to 1). Defaults to 0.5.
    scale : float, optional
        Relative scale of watermark width to video width. Defaults
        to 0.1.

    Raises
    ------
    FileNotFoundError
        If the video or watermark file does not exist.
    Exception
        For other errors related to MoviePy or FFmpeg.
    """
    if not video_path.exists():
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not watermark_image.exists():
        raise FileNotFoundError(f"Watermark image not found: {watermark_image}")
    # Import moviepy lazily to allow importing this module without moviepy
    try:  # pragma: no cover - import time side effects not covered
        from moviepy.editor import VideoFileClip, ImageClip, CompositeVideoClip
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "moviepy must be installed to use watermark functionality."
        ) from e

    logging.info("Loading video %s", video_path)
    video = VideoFileClip(str(video_path))
    vid_w, vid_h = video.size

    logging.info("Loading watermark %s", watermark_image)
    watermark = ImageClip(str(watermark_image))
    # Scale watermark relative to video width
    wm_w = int(vid_w * scale)
    wm_h = int(watermark.h * (wm_w / watermark.w))
    watermark = watermark.resize(width=wm_w)
    # Set opacity
    watermark = watermark.set_opacity(opacity)

    # Determine position
    x_offset, y_offset = _get_position_offsets((vid_w, vid_h), (wm_w, wm_h), position)
    watermark = watermark.set_position((x_offset, y_offset))

    logging.info(
        "Compositing watermark (size %sx%s) at %s with opacity %.2f",
        wm_w,
        wm_h,
        (x_offset, y_offset),
        opacity,
    )
    # Composite the watermark onto the video
    composite = CompositeVideoClip([video, watermark])
    # Write output
    composite.write_videofile(
        str(output_path),
        codec="libx264",
        audio_codec="aac" if video.audio is not None else None,
        temp_audiofile=str(output_path.with_suffix(".m4a")),
        remove_temp=True,
        threads=2,
        logger=None,
    )
    # Release resources
    composite.close()
    video.close()
