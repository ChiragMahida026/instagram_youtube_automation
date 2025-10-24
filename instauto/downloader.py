"""Download Instagram posts using Instaloader.

This module wraps the Instaloader command-line interface rather than the Python
API. Invoking the CLI makes it easy to leverage options like "--fast-update"
for incremental downloads. The implementation groups media files by timestamp
and exposes a simple ``PostInfo`` data class for downstream processing.

Note: This module assumes that the ``instaloader`` executable is available on
your PATH. Install it via pip (``pip install instaloader``) or a system
package manager. The CLI must have access to the internet to fetch Instagram
data.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Iterable


@dataclass
class PostInfo:
    """Container for information about a single Instagram post.

    Attributes
    ----------
    base_name: str
        The timestamp-based prefix used by Instaloader for all files in a post.
    media_files: List[Path]
        List of paths to media files (images or videos) belonging to the post.
    caption: str
        The text caption associated with the post. Empty string if none.
    timestamp: datetime | None
        UTC time extracted from the ``base_name``. When grouping fails the
        timestamp is ``None``.
    """

    base_name: str
    media_files: List[Path]
    caption: str
    timestamp: datetime | None


def _parse_timestamp(base_name: str) -> datetime | None:
    """Parse a timestamp from the Instaloader file prefix.

    Instaloader names files using a pattern like ``YYYY-MM-DD_HH-MM-SS_UTC``.
    This helper parses the date and time and returns a naive ``datetime``
    object in UTC. If the pattern does not match, returns None.
    """
    try:
        return datetime.strptime(base_name, "%Y-%m-%d_%H-%M-%S_UTC")
    except ValueError:
        return None


def _collect_posts(target_dir: Path) -> List[PostInfo]:
    """Collect PostInfo objects from a directory.

    Given a directory containing Instaloader downloads, group media files
    (images/videos) and captions by their common prefix. Returns a list of
    PostInfo sorted by timestamp.
    """
    posts: List[PostInfo] = []
    if not target_dir.exists():
        return posts
    # caption files have .txt extension unless --no-captions was used
    for caption_file in sorted(target_dir.glob("*.txt")):
        base_name = caption_file.stem
        caption = caption_file.read_text(encoding="utf-8", errors="ignore")
        # gather all files starting with base_name excluding .txt and JSON/xz/zip
        media_files = [
            f
            for f in target_dir.glob(f"{base_name}*")
            if f.suffix.lower() not in {".txt", ".json", ".xz", ".zip"}
        ]
        posts.append(
            PostInfo(
                base_name=base_name,
                media_files=sorted(media_files),
                caption=caption.strip(),
                timestamp=_parse_timestamp(base_name),
            )
        )
    # sort by timestamp (None values go last)
    posts.sort(key=lambda p: (p.timestamp is None, p.timestamp))
    return posts


def download_posts(
    profile: str,
    download_all: bool = False,
    output_dir: str | Path = "downloads",
    extra_args: Iterable[str] | None = None,
) -> List[PostInfo]:
    """Download Instagram posts for a profile.

    Parameters
    ----------
    profile: str
        The Instagram username to download. Must be public or you must
        authenticate via Instaloader. If the profile is private you need to
        set up a session file or provide login credentials manually.
    download_all: bool, optional
        When False (default) the function passes ``--fast-update`` to
        Instaloader so it stops downloading at the first existing post. When
        True it fetches all available posts.
    output_dir: str or Path, optional
        Base directory where the profile folder will be created. Defaults
        to ``./downloads``. If the directory does not exist it is created.
    extra_args: iterable of str, optional
        Additional command line flags to pass directly to the ``instaloader``
        executable. Use this to specify login (``--login=myuser``), enable
        stories, reels, etc. Do not include ``--dirname-pattern`` or
        ``--post-metadata-txt`` here — they are set automatically.

    Returns
    -------
    List[PostInfo]
        A list of ``PostInfo`` objects representing downloaded posts. If no
        posts are found (e.g. because Instaloader failed or ``--no-captions``
        was used), an empty list is returned.

    Raises
    ------
    subprocess.CalledProcessError
        If the ``instaloader`` command exits with a non-zero status.
    """
    # ensure output directory exists
    out_base = Path(output_dir)
    out_base.mkdir(parents=True, exist_ok=True)
    target_dir = out_base / profile

    # Compose instaloader CLI command
    cmd: List[str] = ["instaloader"]
    if not download_all:
        cmd.append("--fast-update")  # incremental updates
    # Save caption in .txt files (default) and avoid JSON/xz for simplicity
    cmd.extend(
        [
            "--dirname-pattern",
            str(target_dir),
            "--filename-pattern",
            "{date_utc}_UTC",
            "--post-metadata-txt",
            "{caption}",
            "--no-compress-json",
        ]
    )
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(profile)

    # Execute the command
    subprocess.run(cmd, check=True)
    # Collect posts from output directory
    return _collect_posts(target_dir)

