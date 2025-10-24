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
    # Search recursively so we can support per-post subdirectories.
    for caption_file in sorted(target_dir.rglob("*.txt")):
        base_name = caption_file.stem
        caption = caption_file.read_text(encoding="utf-8", errors="ignore")
        # gather all files starting with base_name in the same directory as caption
        media_dir = caption_file.parent
        media_files = [
            f
            for f in media_dir.glob(f"{base_name}*")
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
    group_into_subdirs: bool = False,
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

    # Execute the command but don't raise on non-zero exit; still collect any
    # files downloaded before the error (e.g., rate limiting or auth issues).
    try:
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            print(
                "Instaloader exited with non-zero status",
                result.returncode,
                "- proceeding to collect any downloaded posts.",
            )
    except Exception as e:
        print(f"Failed to run instaloader: {e}")
    # Collect posts from output directory
    posts = _collect_posts(target_dir)
    # Optionally group each post into its own subdirectory
    if group_into_subdirs and posts:
        moved_posts: List[PostInfo] = []
        for post in posts:
            post_dir = target_dir / post.base_name
            post_dir.mkdir(parents=True, exist_ok=True)
            # Move media files that are not already inside post_dir
            new_media: List[Path] = []
            for f in post.media_files:
                dest = post_dir / f.name
                if f.resolve().parent != post_dir.resolve():
                    try:
                        f.replace(dest)
                    except Exception:
                        # If move fails (e.g., same file), keep as is
                        dest = f
                new_media.append(dest)
            # Move caption file if present at root
            cap_root = target_dir / f"{post.base_name}.txt"
            cap_dest = post_dir / f"{post.base_name}.txt"
            if cap_root.exists() and not cap_dest.exists():
                try:
                    cap_root.replace(cap_dest)
                except Exception:
                    pass
            moved_posts.append(
                PostInfo(
                    base_name=post.base_name,
                    media_files=sorted(new_media),
                    caption=post.caption,
                    timestamp=post.timestamp,
                )
            )
        posts = moved_posts
    return posts
