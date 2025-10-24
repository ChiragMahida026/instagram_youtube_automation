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
from pathlib import Path
from typing import List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

# The OAuth scopes required for uploading videos
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


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
) -> str:
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

    Returns
    -------
    str
        The YouTube video ID of the uploaded video.

    Raises
    ------
    googleapiclient.errors.HttpError
        If the API request fails.
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
        "status": {"privacyStatus": privacy_status},
    }

    # Use resumable upload for reliability
    media = MediaFileUpload(str(video_path), chunksize=-1, resumable=True)
    request = service.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )
    response = None
    try:
        while response is None:
            status, response = request.next_chunk()
            if status:
                # Show progress percentage; this prints to stdout
                percentage = status.progress() * 100
                print(f"Upload progress: {percentage:.2f}%")
        video_id = response.get("id")
        print(f"Video uploaded successfully with ID: {video_id}")
        return video_id
    except HttpError as e:
        print(f"An HTTP error {e.resp.status} occurred:\n{e.content}")
        raise

