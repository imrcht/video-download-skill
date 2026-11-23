# Media Downloader Agent Skill

A tool for autonomous AI agents and developers to download Instagram Reels and YouTube videos (Shorts and long-form) with video, audio, and metadata extraction.

## Features

- **Instagram Reels & Posts**: Supports link-based extraction via Playwright browser automation and persistent session storage.
- **YouTube Shorts & Videos**: Supports direct download of shorts and full-length videos.
- **Audio Extraction**: Extracts audio tracks (MP3 or WAV) using FFmpeg for speech transcription and audio analysis.
- **Agent Output**: Returns structured JSON with absolute local file paths and media metadata.
- **Multi-Agent Skill**: Compatible with Cursor, Claude Code, Antigravity, and OpenAI Codex.

## Quick Start

### 1. Installation

Clone this repository and install dependencies:

```bash
git clone <YOUR_REPOSITORY_URL>
cd instagram-reels-downloader
pip install -r requirements.txt
playwright install chromium
```

### 2. Install as an Agent Skill

Run the installer script to register the skill with your AI coding agents:

```bash
# Install to all detected agents (Cursor, Claude, Antigravity, Codex)
python install.py --all

# Or target a specific agent
python install.py --agent cursor
python install.py --agent claude
python install.py --agent antigravity
```

### 3. Connect Instagram Account

To enable reliable downloading of reels behind login screens:

```bash
python cli.py login --browser
```

A browser window will open. Sign in to Instagram once. The session is preserved in `./browser_data` for subsequent headless downloads.

### 4. CLI Usage

```bash
# Download an Instagram Reel with audio extraction
python cli.py download "https://www.instagram.com/reel/<SHORTCODE>/" --audio

# Download a YouTube Short
python cli.py download "https://www.youtube.com/shorts/<VIDEO_ID>" --audio

# JSON output mode for AI agents
python cli.py download "<URL>" --audio --json

# Check connection and tool status
python cli.py status
```

## Agent Integration

When an AI agent receives a video link, it can execute:

```bash
python cli.py download "<URL>" --audio --json
```

The tool returns:

```json
{
  "status": "success",
  "platform": "instagram",
  "media_type": "reel",
  "url": "<URL>",
  "video_path": "/path/to/video.mp4",
  "audio_path": "/path/to/audio.mp3",
  "metadata_path": "/path/to/metadata.json",
  "duration_seconds": 18.5,
  "views": 250000,
  "likes": 12000,
  "author": "creator",
  "caption": "Video caption text..."
}
```

The agent can then inspect `video_path` for visual content and `audio_path` for speech transcription.

## License

MIT License
