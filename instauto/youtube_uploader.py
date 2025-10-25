"""YouTube uploader using the Data API v3.

This module encapsulates the boilerplate needed to authenticate with Google and
upload videos. It uses OAuth2 via the ``google_auth_oauthlib`` package and
stores credentials in a token file so you only need to authorise once.

According to Google's documentation, each project has a default allocation of
10,000 units per day and each video upload (``videos.insert``) costs 1,600
units. You only pay beyond this quota. See https://developers.google.com/youtube/v3
for details.
"""

from __future__ import annotations

import os
import pickle
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# The OAuth scopes required for uploading videos and checking status
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",  # Full access needed for processing status
    "https://www.googleapis.com/auth/youtube.force-ssl"  # Required for some API operations
]

# Constants for upload retries and processing
MAX_RETRIES = 3
RETRY_DELAYS = [5, 15, 30]  # Seconds to wait between retries
HD_CHECK_INTERVAL = 30  # Seconds between HD processing status checks
HD_CHECK_TIMEOUT = 3600  # Wait up to 1 hour for HD processing
HD_PROCESSING_TIMEOUT = 300  # Wait 5 minutes before first HD check
MIN_CHUNK_SIZE = 1024 * 1024 * 4  # 4MB minimum chunk size for better upload


def get_authenticated_service(
    client_secrets_file: str | Path,
    token_file: str | Path = "youtube_token.pickle",
) -> object:
    """Authenticate and return a YouTube API service object.

    Parameters
    ----------
    client_secrets_file: str or Path
        Path to the JSON file downloaded from the Google Cloud Console. This
        file defines your OAuth client ID and secret.
    token_file: str or Path, optional
        Path where the access/refresh tokens will be cached. Defaults to
        ``youtube_token.pickle`` in the current working directory.

    Returns
    -------
    googleapiclient.discovery.Resource
        An authorised YouTube API service instance.
    """
    creds: Optional[Credentials] = None
    token_path = Path(token_file)
    if token_path.exists():
        with token_path.open("rb") as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, prompt the user to log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(client_secrets_file), SCOPES
            )
            # Launches a browser; the user must authenticate once
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with token_path.open("wb") as token:
            pickle.dump(creds, token)
    return build("youtube", "v3", credentials=creds)


def wait_for_hd_processing(
    service: object,
    video_id: str,
    timeout_secs: int = HD_CHECK_TIMEOUT,
    check_interval: int = HD_CHECK_INTERVAL,
) -> bool:
    """Wait for a video to finish HD processing.
    
    Parameters
    ----------
    service : object
        YouTube API service instance
    video_id : str
        ID of the video to check
    timeout_secs : int, optional
        Maximum seconds to wait, by default 1800 (30 minutes)
    check_interval : int, optional
        Seconds between status checks, by default 30
        
    Returns
    -------
    bool
        True if HD processing completed, False if timeout or processing failed
    """
    start_time = datetime.now()
    while True:
        elapsed = (datetime.now() - start_time).total_seconds()
        if elapsed > timeout_secs:
            print(f"Timeout waiting for HD processing of video {video_id}")
            return False
            
        try:
            response = service.videos().list(
                part="processingDetails,status",
                id=video_id
            ).execute()
            
            if not response.get("items"):
                print(f"Video {video_id} not found")
                return False
                
            status = response["items"][0]
            processing = status.get("processingDetails", {})
            
            # Check if processing is complete
            if processing.get("processingStatus") == "terminated":
                available_qualities = []
                if processing.get("processingProgress", {}).get("partsTotal"):
                    available_qualities = [
                        p.get("processing", {}).get("status")
                        for p in processing.get("availableProcessingQualities", [])
                    ]
                if "hd" in available_qualities or "maxres" in available_qualities:
                    print(f"HD processing complete for video {video_id}")
                    return True
                print(f"Processing complete but HD not available for {video_id}")
                return False
                
            # Still processing
            progress = processing.get("processingProgress", {})
            if progress and progress.get("partsTotal"):
                pct = (progress.get("partsProcessed", 0) / progress.get("partsTotal")) * 100
                print(f"HD processing progress for {video_id}: {pct:.1f}%")
            else:
                print(f"Waiting for HD processing to begin for {video_id}")
                
        except Exception as e:
            print(f"Error checking processing status: {e}")
            
        time.sleep(check_interval)


def upload_video(
    video_path: str | Path,
    title: str,
    description: str,
    tags: Optional[List[str]] = None,
    category_id: str = "22",
    privacy_status: str = "public",
    client_secrets_file: str | Path | None = None,
    token_file: str | Path = "youtube_token.pickle",
    service: object | None = None,
    wait_for_hd: bool = True,
    test_mode: bool = False,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """Upload a single video to YouTube.

    Either provide an existing authenticated ``service`` object or set
    ``client_secrets_file`` and optionally ``token_file`` to construct one on
    the fly. On success the function returns the ID of the uploaded video.

    Parameters
    ----------
    video_path: str or Path
        Path to the video file (.mp4, .mov, etc.).
    title: str
        Title of the video on YouTube.
    description: str
        Full description text. Should include hashtags and credits as desired.
    tags: list of str, optional
        Tags/keywords for the video. Can be None.
    category_id: str, optional
        The numeric category ID as defined by YouTube. Default is "22"
        (People & Blogs). See YouTube documentation for a full list.
    privacy_status: str, optional
        One of "public", "private" or "unlisted". Default is "public".
    client_secrets_file: str or Path, optional
        Path to OAuth client secrets. Required if ``service`` is None.
    token_file: str or Path, optional
        Where to cache credentials. Defaults to ``youtube_token.pickle``.
    service: googleapiclient.discovery.Resource, optional
        An existing YouTube API client. If supplied the function will not
        re-authenticate.
    wait_for_hd: bool, optional
        Whether to wait for HD processing to complete before returning.
        Default is True.
    test_mode: bool, optional
        If True, validates the upload request but doesn't actually upload.
        Useful for testing configuration. Default is False.

    Returns
    -------
    tuple
        A tuple containing (video_id, details_dict) where:
        - video_id (str or None): The YouTube video ID if upload succeeded, None if failed
        - details_dict (dict): Upload details including:
            - success (bool): Whether upload completed successfully
            - hd_ready (bool): Whether HD processing completed (if wait_for_hd=True)
            - error (str): Error message if any
            - retries (int): Number of retries attempted
            - test_only (bool): Whether this was a test run

    Raises
    ------
    RuntimeError
        If neither ``service`` nor ``client_secrets_file`` is provided.
    """
    # Build or use provided service
    if service is None:
        if client_secrets_file is None:
            raise RuntimeError(
                "Either provide a YouTube API service or a client secrets file"
            )
        service = get_authenticated_service(client_secrets_file, token_file)

    # Prepare the request body
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags or [],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False  # Required for HD processing
        }
    }

    if test_mode:
        # In test mode, validate inputs and return test results
        try:
            media = MediaFileUpload(
                str(video_path),
                mimetype='video/mp4',
                chunksize=256 * 1024,
                resumable=True
            )
            if not media.has_stream():
                return None, {
                    "success": False,
                    "hd_ready": False,
                    "error": "Video file cannot be read or is invalid",
                    "retries": 0,
                    "test_only": True
                }
            return "TEST_MODE", {
                "success": True,
                "hd_ready": False,
                "error": None,
                "retries": 0,
                "test_only": True,
                "file_size": media.size(),
                "mime_type": media.mimetype(),
                "valid_body": body
            }
        except Exception as e:
            return None, {
                "success": False,
                "hd_ready": False,
                "error": str(e),
                "retries": 0,
                "test_only": True
            }

    # Prepare upload with retries
    result = {
        "success": False,
        "hd_ready": False,
        "error": None,
        "retries": 0,
        "test_only": False
    }
    
    for attempt in range(MAX_RETRIES):
        try:
            if attempt > 0:
                print(f"Retry attempt {attempt} for {video_path}")
                time.sleep(RETRY_DELAYS[attempt - 1])
            
            # Configure for HD upload
            media = MediaFileUpload(
                str(video_path),
                mimetype=None,  # Let YouTube auto-detect for better format support
                chunksize=1024 * 1024 * 4,  # Use 4MB chunks for better upload
                resumable=True
            )
            
            # Set processing preferences for HD
            body["status"]["embeddable"] = True  # Allow embedding for better processing
            body["status"]["license"] = "youtube"  # Standard YouTube license
            body["status"]["publicStatsViewable"] = True  # Required for some processing features
            
            # Use insert with specific processing preferences
            request = service.videos().insert(
                part="snippet,status,recordingDetails",
                body=body,
                media_body=media,
                notifySubscribers=False,  # Don't notify until HD is ready
                autoLevels=False,  # Preserve original quality
                stabilize=False,  # Don't apply stabilization that might reduce quality
            )
            
            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    percentage = status.progress() * 100
                    print(f"Upload progress: {percentage:.2f}%")
            
            video_id = response.get("id")
            if not video_id:
                raise RuntimeError("Upload succeeded but no video ID returned")
                
            print(f"Video uploaded successfully with ID: {video_id}")
            result["success"] = True
            
            # Wait for HD processing if requested
            if wait_for_hd:
                print("Waiting for HD processing to complete...")
                result["hd_ready"] = wait_for_hd_processing(service, video_id)
            
            return video_id, result
            
        except HttpError as e:
            content = e.content or b""
            try:
                reason_text = content.decode("utf-8", errors="ignore")
            except Exception:
                reason_text = str(content)
            
            result["error"] = reason_text
            result["retries"] = attempt + 1
            
            # Don't retry quota/upload limit errors
            if e.resp is not None and getattr(e.resp, "status", None) == 400 and (
                "uploadLimitExceeded" in reason_text or 
                "The user has exceeded the number of videos they may upload" in reason_text
            ):
                print("Upload limit reached for this account. Further uploads will be skipped.")
                return None, result
            
            # Don't retry bad requests
            if e.resp is not None and getattr(e.resp, "status", None) == 400:
                print(f"Bad request error: {reason_text}")
                return None, result
                
            # Log the error and continue to retry
            print(f"Upload attempt {attempt + 1} failed: {reason_text}")
            if attempt < MAX_RETRIES - 1:
                print(f"Will retry in {RETRY_DELAYS[attempt]} seconds...")
            
        except Exception as e:
            result["error"] = str(e)
            result["retries"] = attempt + 1
            print(f"Upload attempt {attempt + 1} failed with error: {e}")
            if attempt < MAX_RETRIES - 1:
                print(f"Will retry in {RETRY_DELAYS[attempt]} seconds...")
    
    print(f"Upload failed after {MAX_RETRIES} attempts")
    return None, result

