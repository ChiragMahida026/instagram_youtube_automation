"""Top‑level package for the Instagram‑YouTube automation system.

This package exposes a minimal API for downloading Instagram posts, generating
YouTube metadata and uploading videos.  See individual modules for details.
"""

from .downloader import download_posts, PostInfo
from .summarizer import generate_title_description
from .youtube_uploader import upload_video

__all__ = [
    "download_posts",
    "PostInfo",
    "generate_title_description",
    "upload_video",
]