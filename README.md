# Instagram‑YouTube Automation System

## Overview

This project implements a **zero‑cost automation pipeline** that downloads posts from Instagram, organises the media and captions into a local archive and optionally republishes video posts on YouTube.  It was designed to minimise or eliminate subscription fees – the only paid component is the YouTube Data API quota if you exceed Google’s generous free allocation.  All other pieces, including the Instagram scraper and summarisation logic, rely on open source or free services.

### Key Features

1. **Flexible downloads**: specify one or more Instagram usernames and choose between downloading **all** content or only **new posts** since the last run.  The system leverages [Instaloader](https://instaloader.github.io/) to archive photos, videos, Reels and captions.  Instaloader is free and, by default, saves a `.txt` file alongside each post that contains the post’s caption【503652632033799†L146-L152】【503652632033799†L303-L312】.  When the `--fast‑update` option is used the tool stops at the first already downloaded post, which is ideal for incremental updates【503652632033799†L146-L153】.
2. **Structured storage**: posts are stored in folders named after each username.  For each post, the code gathers all media files (e.g. multiple photos or video and thumbnail) that share the same base timestamp and writes the caption into a corresponding metadata JSON file.  This makes it easy to locate media and associated text.
3. **Automatic title and description generation**: the default title is a cleaned version of the first sentence of the caption (with hashtags removed); the description contains the full caption.  Long captions can optionally be summarised using the OpenAI API if you provide your own `OPENAI_API_KEY`.  You can also adopt Zapier’s advice and map the Instagram caption directly to the YouTube title and description【530634502660156†L414-L417】.
4. **YouTube uploading**: a dedicated module uses the YouTube Data API (v3) to upload video files.  The API is free up to a quota of **10 000 units per day**; uploading a video costs **1 600 units** per call【456953751346438†L129-L135】【652280474570090†L121-L133】.  You only pay beyond this quota or if you voluntarily upgrade.  The uploader handles authentication (OAuth2) and supports resumable uploads.
5. **Test coverage**: the repository includes unit tests that mock out external dependencies so you can verify the logic without hitting Instagram or YouTube.  Running the tests produces a coverage report to identify any untested code paths.

## Installation

1. **Clone the repository**:

   ```sh
   git clone https://github.com/<your‑username>/<your‑repo>.git
   cd <your‑repo>
   ```

2. **Create a Python environment** (recommended):

   ```sh
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies**:

   ```sh
   pip install -r requirements.txt
   ```

   The requirements include `instaloader` (for scraping), `google‑api‑python‑client` and `oauth2client` (for YouTube), `pytest` and `coverage` (for testing) and `openai` (optional summarisation).

## Usage

The entry point for the pipeline is `main.py`.  Run the script with one or more Instagram usernames and choose whether to download all posts or only new posts:

```sh
python main.py \
  --usernames nasa nasa.tourism \
  --download-all        # omit this flag to fetch only new posts
  --output-dir /path/to/archive \
  --upload-videos       # omit to skip YouTube uploads
  --use-chatgpt         # optional: summarise captions via OpenAI API
```

### Flags

* `--usernames`: Comma‑separated list of Instagram usernames to process.
* `--download-all`: Fetch the entire history of posts.  Without this flag the script passes `--fast‑update` to Instaloader so it stops when it encounters previously downloaded content【503652632033799†L146-L153】.
* `--output-dir`: Where to store downloaded media and metadata.  Default is `./downloads`.
* `--upload-videos`: If set, the script will upload any new video files to YouTube.  You must configure API credentials as described below.
* `--use-chatgpt`: Generate titles and descriptions by calling the OpenAI API.  Requires setting the environment variable `OPENAI_API_KEY` with your own key.  Without this flag the script derives a title from the caption and uses the full caption as the description, as recommended by Zapier【530634502660156†L414-L417】.

### Configuration for YouTube Uploads

1. **Create a Google Cloud project** and enable the **YouTube Data API v3**.  Follow Google’s instructions to obtain OAuth client credentials.  For an installed application you will download a `client_secret.json` file.
2. Place the `client_secret.json` file in the project root or set the `GOOGLE_CLIENT_SECRETS_FILE` environment variable pointing to it.
3. The first time you run the script with `--upload-videos` you will be asked to authenticate in the browser.  Afterwards a token file is saved (`youtube_token.json` by default) and reused.

YouTube provides **10 000 units** of API quota per project per day【456953751346438†L129-L135】.  Each video upload (`videos.insert`) consumes **1 600 units**【652280474570090†L121-L133】, so you can upload roughly six videos per day without requesting additional quota.

### Running as a scheduled task

To automate the pipeline, set up a scheduled task (cron on Linux/macOS or Task Scheduler on Windows).  For example, to run every day at 7 AM on Linux:

```sh
0 7 * * * /path/to/venv/bin/python /path/to/main.py --usernames myprofile --output-dir /path/to/archive --upload-videos
```

The `--fast‑update` behaviour ensures only new posts are downloaded during each run【503652632033799†L146-L153】.

## Code Structure

* `main.py` – Orchestrates the pipeline: downloads posts, processes metadata, generates titles/descriptions and optionally uploads videos.
* `instauto/downloader.py` – Wraps Instaloader CLI to fetch posts for a profile.  Groups media files by timestamp and reads captions into Python objects.
* `instauto/processor.py` – Functions to group media files, sanitise captions and prepare metadata.
* `instauto/summarizer.py` – Generates YouTube titles and descriptions.  Can use simple heuristics or call the OpenAI API.
* `instauto/youtube_uploader.py` – Handles OAuth2 authentication and video uploads to YouTube.
* `tests/` – Unit tests that mock out external dependencies and verify grouping logic, summarisation and upload calls.

## Tests and Coverage

Run all tests with:

```sh
pytest
```

To generate a coverage report:

```sh
coverage run -m pytest
coverage html
```

This will produce an `htmlcov` directory containing a detailed coverage report.  Aim for a high coverage percentage; the existing tests provide good baseline coverage but feel free to add more.

## Notes on Free Usage

* **Instaloader is free and open source** under the MIT licence.  It supports incremental updates via `--fast‑update` or `--latest-stamps` so you don’t waste bandwidth downloading old posts【503652632033799†L146-L153】.
* The **YouTube Data API** has a generous free quota.  According to Google’s documentation, each project has a default allocation of **10 000 units per day**【456953751346438†L129-L135】 and a single video upload costs **1 600 units**【652280474570090†L121-L133】.
* **OpenAI summarisation is optional**.  If you have an API key (e.g. via a ChatGPT subscription) you can set `OPENAI_API_KEY` to enable the summariser.  Without it, the code uses simple heuristics and caption mapping as recommended by Zapier【530634502660156†L414-L417】.

## Contributing

Pull requests are welcome.  Please ensure any new features include appropriate tests and documentation.  If you encounter issues with Instaloader or the YouTube API, consult their upstream documentation and open an issue in this repository.