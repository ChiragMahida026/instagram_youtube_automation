"""Command-line entry point for the Instagram-YouTube automation pipeline.

This script ties together downloading posts, generating YouTube metadata and
optionally uploading videos. It is designed for repeated execution: if
"--download-all" is not specified it uses Instaloader's "--fast-update" to
avoid fetching previously downloaded posts. Metadata is stored alongside each
post in a ".json" file so the script can skip videos that have already been
uploaded.

Usage example:

    python main.py \
        --usernames nasa,spacex \
        --output-dir ./archive \
        --use-chatgpt \
        --upload-videos \
        --client-secrets client_secret.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import List

import instauto.downloader as downloader
import instauto.summarizer as summarizer
from instauto.youtube_uploader import upload_video, get_authenticated_service
from googleapiclient.errors import HttpError

# Constants for upload throttling
MAX_UPLOADS_PER_DAY = 5  # Adjust based on your channel limits
UPLOAD_SPACING_SECONDS = 60  # 1 minute between uploads


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
    watermark_image: Path | None = None,
    watermark_opts: dict | None = None,
    instaloader_args: list[str] | None = None,
    per_post_subdirs: bool = False,
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
        Keyword arguments forwarded to the YouTube upload functions. Should
        include "client_secrets_file", "token_file", "category_id" and
        "privacy_status" if needed.
    """
    if instaloader_args is None and not per_post_subdirs:
        posts = downloader.download_posts(
            username,
            download_all=download_all,
            output_dir=output_dir,
        )
    elif instaloader_args is None and per_post_subdirs:
        posts = downloader.download_posts(
            username,
            download_all=download_all,
            output_dir=output_dir,
            group_into_subdirs=True,
        )
    elif instaloader_args is not None and not per_post_subdirs:
        posts = downloader.download_posts(
            username,
            download_all=download_all,
            output_dir=output_dir,
            extra_args=instaloader_args,
        )
    else:
        posts = downloader.download_posts(
            username,
            download_all=download_all,
            output_dir=output_dir,
            extra_args=instaloader_args,
            group_into_subdirs=True,
        )
    profile_dir = Path(output_dir) / username
    uploads_this_run = 0
    for post in posts:
        # If we hit a YouTube upload limit during this run, stop attempting
        # further uploads for subsequent posts to avoid repeated failures.
        
        # Check daily upload limit
        if uploads_this_run >= MAX_UPLOADS_PER_DAY:
            print(f"Reached daily upload limit of {MAX_UPLOADS_PER_DAY} videos. Stopping further uploads.")
            break
        if upload_videos and service_params.get("_upload_limit_reached"):
            # still generate metadata but skip uploads
            upload_for_this_post = False
        else:
            upload_for_this_post = upload_videos
        # metadata file path
        if per_post_subdirs and (profile_dir / post.base_name).exists():
            meta_path = (profile_dir / post.base_name) / "meta.json"
        else:
            meta_path = profile_dir / f"{post.base_name}_meta.json"
        # Check all metadata files in the profile directory to avoid duplicates
        title, description = summarizer.generate_title_description(
            post.caption, use_chatgpt=use_chatgpt
        )
        
        # First check if this post's metadata exists
        existing_meta = None
        if meta_path.exists():
            try:
                with meta_path.open("r", encoding="utf-8") as f:
                    existing_meta = json.load(f)
                if existing_meta.get("uploaded"):
                    print(f"Skipping already processed post: {post.caption[:50]}...")
                    continue
            except Exception:
                existing_meta = None

        # Then check all other metadata files to avoid duplicate content
        skip_post = False
        for meta_file in profile_dir.glob("**/*meta.json"):
            if meta_file == meta_path:
                continue
            try:
                with meta_file.open("r", encoding="utf-8") as f:
                    other_meta = json.load(f)
                    if other_meta.get("title") == title or other_meta.get("description") == description:
                        print(f"Skipping duplicate content found in {meta_file}")
                        skip_post = True
                        break
            except Exception:
                continue
                
        if skip_post:
            continue
        # Generate title and description
        title, description = summarizer.generate_title_description(
            post.caption, use_chatgpt=use_chatgpt
        )
        # Extract hashtags for tags list
        tags = extract_hashtags(post.caption)
        # Initialize metadata with content information for duplicate detection
        meta = {
            "caption": post.caption,
            "title": title,
            "description": description,
            "tags": tags,
            "uploaded": False,
            "video_ids": [],
            "uploads": [],
            "content_hash": hashlib.md5(f"{title}{description}".encode()).hexdigest(),
            "first_seen": datetime.now().isoformat()
        }
        if existing_meta:
            # preserve previously recorded successful uploads
            meta.update({
                "video_ids": existing_meta.get("video_ids", []) or [],
                "uploads": existing_meta.get("uploads", []) or [],
            })
        # Upload videos if requested
        if upload_for_this_post:
            # Build or reuse service
            service = get_authenticated_service(
                client_secrets_file=service_params.get("client_secrets_file"),
                token_file=service_params.get("token_file", "youtube_token.pickle"),
            )
            for media in post.media_files:
                if media.suffix.lower() not in {".mp4", ".mov", ".avi", ".mkv"}:
                    # skip non-video files
                    continue
                video_path = media
                # If this exact media filename has already been uploaded in a
                # previous run, skip it. This prevents re-uploading when the
                # script was interrupted after an upload but before writing
                # the final metadata file.
                if media.name in meta.get("uploads", []):
                    print(f"Skipping already-uploaded media: {media}")
                    continue
                # Apply watermark if requested
                if watermark_image is not None:
                    try:
                        from instauto.watermark import apply_watermark

                        wm_output = video_path.with_name(f"{video_path.stem}_wm{video_path.suffix}")
                        opts = watermark_opts or {}
                        apply_watermark(
                            video_path=video_path,
                            watermark_image=watermark_image,
                            output_path=wm_output,
                            position=opts.get("position", "bottom-right"),
                            opacity=opts.get("opacity", 0.5),
                            scale=opts.get("scale", 0.1),
                        )
                        video_path = wm_output
                    except Exception as e:
                        print(f"Failed to apply watermark to {media}: {e}")
                        # continue with original file if watermark failed
                try:
                    video_id, upload_details = upload_video(
                        video_path=video_path,
                        title=title,
                        description=description,
                        tags=tags,
                        category_id=service_params.get("category_id", "22"),
                        privacy_status=service_params.get("privacy_status", "public"),
                        service=service,
                        wait_for_hd=True,  # Wait for HD processing
                        test_mode=service_params.get("test_mode", False)  # Support test mode
                    )
                    
                    if not upload_details["success"]:
                        print(f"Upload failed for {media}: {upload_details['error']}")
                        if "uploadLimitExceeded" in str(upload_details.get("error", "")):
                            service_params["_upload_limit_reached"] = True
                            print("Stopping further uploads due to upload limit.")
                            break
                        continue
                        
                    if video_id is None or video_id == "TEST_MODE":
                        if upload_details.get("test_only"):
                            print(f"Test mode - would have uploaded: {media}")
                            print(f"Test details: {json.dumps(upload_details, indent=2)}")
                            continue
                        else:
                            print(f"Upload failed for {media} with no error")
                            continue
                            
                    # Record the successful upload immediately
                    meta["video_ids"].append(video_id)
                    meta["uploads"].append(media.name)
                    meta.setdefault("upload_details", {})[media.name] = {
                        "video_id": video_id,
                        "uploaded_at": datetime.now().isoformat(),
                        "hd_ready": upload_details.get("hd_ready", False),
                        "retries": upload_details.get("retries", 0)
                    }
                    
                    # ensure profile dir exists before writing incremental meta
                    profile_dir.mkdir(parents=True, exist_ok=True)
                    with meta_path.open("w", encoding="utf-8") as f:
                        json.dump(meta, f, ensure_ascii=False, indent=2)

                    uploads_this_run += 1

                    # Sleep between uploads to avoid rate limits
                    if uploads_this_run < MAX_UPLOADS_PER_DAY:
                        time.sleep(UPLOAD_SPACING_SECONDS)
                        
                except HttpError as e:
                    if e.resp.status == 400 and any(err.get('reason') == 'uploadLimitExceeded' for err in e.error_details or []):
                        print("Hit YouTube daily upload cap. Halting this run.")
                        service_params["_upload_limit_reached"] = True
                        break
                    else:
                        print(f"Failed to upload {media}: {e}")
                except Exception as e:
                    print(f"Failed to upload {media}: {e}")
            # Mark as uploaded only if at least one video was successfully
            # uploaded. Persist final metadata for completeness.
            meta["uploaded"] = bool(meta["video_ids"])
        # Persist metadata (also covers the case where no upload was
        # attempted but meta was generated/updated). Ensure parent dir
        # exists before writing.
        profile_dir.mkdir(parents=True, exist_ok=True)
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Instagram posts and optionally upload videos to YouTube."
    )
    parser.add_argument(
        "--usernames",
        required=True,
        help="Comma-separated list of Instagram usernames (without @)",
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
        help="YouTube category ID for uploaded videos (default: 22 - People & Blogs)",
    )
    parser.add_argument(
        "--privacy-status",
        default="public",
        choices=["public", "unlisted", "private"],
        help="Privacy status for uploaded videos",
    )
    parser.add_argument(
        "--watermark-image",
        dest="watermark_image",
        default=None,
        help="Path to a PNG file to overlay as a watermark on videos before uploading",
    )
    parser.add_argument(
        "--watermark-position",
        dest="watermark_position",
        default="bottom-right",
        choices=["top-left", "top-right", "bottom-left", "bottom-right"],
        help=(
            "Position of the watermark on the video (default: bottom-right). "
            "Requires --watermark-image."
        ),
    )
    parser.add_argument(
        "--watermark-opacity",
        dest="watermark_opacity",
        type=float,
        default=0.5,
        help="Opacity of the watermark (0.0 to 1.0, default: 0.5). Requires --watermark-image.",
    )
    parser.add_argument(
        "--watermark-scale",
        dest="watermark_scale",
        type=float,
        default=0.1,
        help=(
            "Relative scale of watermark width to video width (default: 0.1). "
            "Requires --watermark-image."
        ),
    )
    parser.add_argument(
        "--instaloader-args",
        default=None,
        help=(
            "Additional arguments to pass to instaloader CLI, e.g. \"--login USER --sessionfile path\". "
            "Useful to authenticate and avoid rate limits."
        ),
    )
    parser.add_argument(
        "--per-post-subdirs",
        action="store_true",
        help=(
            "Store each post inside a subdirectory named after its timestamp prefix. "
            "Metadata will be written as 'meta.json' inside each subdirectory."
        ),
    )
    parser.add_argument(
        "--test-mode",
        action="store_true",
        help=(
            "Run in test mode - validate videos and settings but don't actually upload. "
            "Useful for checking configuration and video files."
        ),
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
        "test_mode": args.test_mode,
    }
    # Build watermark options
    # Validate watermark image early so we fail fast if the file does not
    # exist. If the user provided a relative path it will be resolved against
    # the current working directory.
    watermark_image = None
    watermark_opts = None
    if args.watermark_image:
        candidate = Path(args.watermark_image).expanduser()
        try:
            candidate = candidate.resolve()
        except Exception:
            # resolving may fail in some environments; keep the candidate
            pass
        if not candidate.exists():
            print(f"Watermark image not found: {args.watermark_image}\nPlease provide an absolute path or place the file in the current working directory.")
            # disable watermarking to avoid repeating the same error per file
            watermark_image = None
        else:
            watermark_image = candidate
            watermark_opts = {
                "position": args.watermark_position,
                "opacity": args.watermark_opacity,
                "scale": args.watermark_scale,
            }
    # Parse optional instaloader extra args
    import shlex
    instaloader_args = shlex.split(args.instaloader_args) if args.instaloader_args else None
    for username in usernames:
        process_profile(
            username=username,
            download_all=args.download_all,
            output_dir=output_dir,
            upload_videos=args.upload_videos,
            use_chatgpt=args.use_chatgpt,
            service_params=service_params,
            watermark_image=watermark_image,
            watermark_opts=watermark_opts,
            instaloader_args=instaloader_args,
            per_post_subdirs=args.per_post_subdirs,
        )


if __name__ == "__main__":
    main()
