"""Command‑line entry point for the Instagram‑YouTube automation pipeline.

This script ties together downloading posts, generating YouTube metadata and
optionally uploading videos.  It is designed for repeated execution: if
`--download-all` is not specified it uses Instaloader’s `--fast‑update` to
avoid fetching previously downloaded posts【503652632033799†L146-L153】.  Metadata is stored
alongside each post in a `.json` file so the script can skip videos that
have already been uploaded.

Usage example:

```sh
python main.py \
    --usernames nasa,spacex \
    --output-dir ./archive \
    --use-chatgpt \
    --upload-videos \
    --client-secrets client_secret.json
```
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import List

from instauto.downloader import download_posts, PostInfo
from instauto.summarizer import generate_title_description
from instauto.youtube_uploader import upload_video, get_authenticated_service


def extract_hashtags(text: str) -> List[str]:
    """Return a list of hashtags (without the leading '#') in the given text."""
    return [tag.strip("#") for tag in re.findall(r"#[\w\d_]+", text)]


def process_profile(
    username: str,
    download_all: bool,
    output_dir: Path,
    upload_videos: bool,
    use_chatgpt: bool,
    service_params: dict,
) -> None:
    """Download, process and optionally upload posts for a single profile.

    Parameters
    ----------
    username: str
        Instagram handle (without @).
    download_all: bool
        If False, only new posts are fetched.
    output_dir: Path
        Directory where downloaded files and metadata are stored.
    upload_videos: bool
        Whether to upload videos to YouTube.
    use_chatgpt: bool
        Whether to call the OpenAI API to summarise captions.
    service_params: dict
        Keyword arguments forwarded to the YouTube upload functions.  Should
        include `client_secrets_file`, `token_file`, `category_id` and
        `privacy_status` if needed.
    """
    posts = download_posts(username, download_all=download_all, output_dir=output_dir)
    profile_dir = Path(output_dir) / username
    for post in posts:
        # metadata file path
        meta_path = profile_dir / f"{post.base_name}_meta.json"
        # Skip processing if metadata exists and indicates uploaded
        if meta_path.exists():
            try:
                with meta_path.open("r", encoding="utf-8") as f:
                    meta = json.load(f)
                if meta.get("uploaded"):
                    # already processed
                    continue
            except Exception:
                # if file is corrupt, continue to regenerate
                pass
        # Generate title and description
        title, description = generate_title_description(post.caption, use_chatgpt=use_chatgpt)
        # Extract hashtags for tags list
        tags = extract_hashtags(post.caption)
        meta = {
            "caption": post.caption,
            "title": title,
            "description": description,
            "tags": tags,
            "uploaded": False,
            "video_ids": [],
        }
        # Upload videos if requested
        if upload_videos:
            # Build or reuse service
            service = get_authenticated_service(
                client_secrets_file=service_params.get("client_secrets_file"),
                token_file=service_params.get("token_file", "youtube_token.pickle"),
            )
            for media in post.media_files:
                if media.suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv"}:
                    # skip non‑video files
                    continue
                try:
                    video_id = upload_video(
                        video_path=media,
                        title=title,
                        description=description,
                        tags=tags,
                        category_id=service_params.get("category_id", "22"),
                        privacy_status=service_params.get("privacy_status", "public"),
                        service=service,
                    )
                    meta["video_ids"].append(video_id)
                except Exception as e:
                    print(f"Failed to upload {media}: {e}")
            # Mark as uploaded only if at least one video was successfully uploaded
            meta["uploaded"] = bool(meta["video_ids"])
        # Persist metadata
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Instagram posts and optionally upload videos to YouTube."
    )
    parser.add_argument(
        "--usernames",
        required=True,
        help="Comma‑separated list of Instagram usernames (without @)",
    )
    parser.add_argument(
        "--download-all",
        action="store_true",
        help="Download all posts instead of only new posts",
    )
    parser.add_argument(
        "--output-dir",
        default="downloads",
        help="Directory where downloads and metadata are stored",
    )
    parser.add_argument(
        "--upload-videos",
        action="store_true",
        help="Upload downloaded videos to YouTube",
    )
    parser.add_argument(
        "--use-chatgpt",
        action="store_true",
        help="Use OpenAI API to summarise captions for titles and descriptions",
    )
    parser.add_argument(
        "--client-secrets",
        dest="client_secrets_file",
        default=None,
        help="Path to Google OAuth client secrets JSON file (required for uploading)",
    )
    parser.add_argument(
        "--token-file",
        default="youtube_token.pickle",
        help="File to cache OAuth tokens (default: youtube_token.pickle)",
    )
    parser.add_argument(
        "--category-id",
        default="22",
        help="YouTube category ID for uploaded videos (default: 22 – People & Blogs)",
    )
    parser.add_argument(
        "--privacy-status",
        default="public",
        choices=["public", "unlisted", "private"],
        help="Privacy status for uploaded videos",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    usernames = [u.strip() for u in args.usernames.split(",") if u.strip()]
    output_dir = Path(args.output_dir)
    # Build service params only once
    service_params = {
        "client_secrets_file": args.client_secrets_file,
        "token_file": args.token_file,
        "category_id": args.category_id,
        "privacy_status": args.privacy_status,
    }
    for username in usernames:
        process_profile(
            username=username,
            download_all=args.download_all,
            output_dir=output_dir,
            upload_videos=args.upload_videos,
            use_chatgpt=args.use_chatgpt,
            service_params=service_params,
        )


if __name__ == "__main__":
    main()