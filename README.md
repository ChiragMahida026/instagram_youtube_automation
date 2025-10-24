Instagram–YouTube Automation System
==================================

Overview
--------

This project implements a zero-cost automation pipeline that downloads posts
from Instagram, organises the media and captions into a local archive and
optionally republishes video posts on YouTube. All components are free to use;
the only paid element is YouTube API quota if you exceed Google’s free
allocation.

Key Features
------------

- Flexible downloads: process one or more Instagram usernames and choose to
  download all content or only new posts since the last run (via Instaloader’s
  ``--fast-update``).
- Structured storage: media and captions are grouped per post and saved under
  a folder for each username.
- Automatic metadata: generate YouTube titles and descriptions from captions,
  with an optional OpenAI-powered summariser.
- YouTube uploading: upload videos via the YouTube Data API v3 with OAuth2
  authentication and resumable uploads.
- Tests included: unit tests mock external services to validate logic.
- Optional watermarking: overlay a PNG watermark on videos prior to upload.

Installation
------------

1. Clone the repository:

       git clone https://github.com/<your-username>/<your-repo>.git
       cd <your-repo>

2. (Recommended) Create a virtual environment and install dependencies:

       python -m venv .venv
       .venv\Scripts\activate  # Windows
       # source .venv/bin/activate  # macOS/Linux
       pip install -r requirements.txt

Usage
-----

Run the pipeline with one or more Instagram usernames. By default only new
posts are fetched; pass ``--download-all`` to fetch the entire history.

    python main.py \
      --usernames nasa,spacex \
      --output-dir ./downloads \
      --upload-videos \
      --use-chatgpt \
      --client-secrets client_secret.json \
      --watermark-image ./logo.png \
      --watermark-position bottom-right \
      --watermark-opacity 0.5 \
      --watermark-scale 0.1

Flags
-----

- ``--usernames``: Comma-separated list of Instagram usernames to process.
- ``--download-all``: Fetch the entire history; otherwise only new posts are
  downloaded using Instaloader’s fast-update.
- ``--output-dir``: Directory for downloads and metadata (default: ``./downloads``).
- ``--upload-videos``: Upload any downloaded videos to YouTube (requires API
  credentials).
- ``--use-chatgpt``: Use OpenAI to summarise captions (requires
  ``OPENAI_API_KEY`` set in the environment).
- ``--watermark-*``: Optional watermark controls. Requires ``--watermark-image``.

YouTube Setup
-------------

1. Create a Google Cloud project and enable the YouTube Data API v3.
2. Download OAuth client credentials (``client_secret.json``) and either place
   it in the project root or pass the path via ``--client-secrets``.
3. On first upload you will be prompted to authenticate; a token will be
   cached locally for future runs.

Tests
-----

Run tests and (optionally) generate a coverage report:

    pytest
    coverage run -m pytest && coverage html

Notes
-----

- Instaloader is free and supports incremental updates via ``--fast-update``.
- The YouTube Data API provides a generous free daily quota; uploads cost a
  fixed number of units each.
- OpenAI summarisation is optional; without a key the code uses a simple
  heuristic for titles and descriptions.

