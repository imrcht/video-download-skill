---
name: media-downloader
description: >-
  Automatically download Instagram Reels, YouTube Shorts, and YouTube long-form videos given a link or URL.
  Extracts high-quality MP4 video and MP3 audio with full metadata for AI agents to analyze visual and audio references.
  Use whenever the user provides an Instagram reel link or YouTube link and asks to inspect, summarize, transcribe,
  analyze, critique, recreate, or extract audio/video content.
---

# Media Downloader — Agent Skill (Instagram Reels & YouTube)

This skill equips AI agents (Cursor, Claude Code, Codex, Antigravity, etc.) with the ability to automatically download video and audio content from **Instagram Reels** and **YouTube (Shorts & Long-form)** whenever a link is provided.

---

## 🎯 Why AI Agents Need This Skill

When a user pastes an Instagram Reel link or YouTube link into an AI conversation:
1. **AI Agents are "Deaf" to Web Links**: Agents cannot listen to online video links. Even if an agent has a web browser tool, it only captures silent screenshots — completely missing spoken words, voice tone, background music, audio cues, and sound effects.
2. **Instagram Blocks Direct Scraping**: Instagram requires authenticated sessions and blocks standard HTTP scrapers with login gates and rate limits.
3. **Multimodal Analysis Requires Local Files**: To transcribe speech (via Whisper or Gemini multimodal audio) and analyze video pacing or visuals, agents must have the actual `.mp4` and `.mp3` files stored locally.

This skill bridges the gap: the agent runs a single command, downloads the video, extracts an `.mp3` audio track, and receives a clean JSON payload containing local file paths and metadata.

---

## 🚀 How the Agent Should Execute

Whenever the user provides an Instagram Reel or YouTube URL and asks to review, transcribe, summarize, or reference it:

### Step 1: Run the Downloader via CLI
Execute the following command in the workspace:

```bash
python cli.py download "<URL>" --audio --json
```

*(Note: If calling from outside the repository root, invoke `python <path-to-repo>/cli.py download "<URL>" --audio --json`)*

### Step 2: Parse the Machine-Readable JSON Output
The command returns a JSON object on standard output:

```json
{
  "status": "success",
  "platform": "instagram",
  "media_type": "reel",
  "url": "https://www.instagram.com/reel/C8xyz123/",
  "video_path": "D:/instagram-reels-downloader/downloads/instagram/C8xyz123.mp4",
  "audio_path": "D:/instagram-reels-downloader/downloads/instagram/C8xyz123.mp3",
  "metadata_path": "D:/instagram-reels-downloader/downloads/instagram/C8xyz123_meta.json",
  "duration_seconds": 18.5,
  "views": 245000,
  "likes": 18200,
  "author": "creator_name",
  "caption": "Hook line and full caption text...",
  "date": "2026-05-10"
}
```

### Step 3: Utilize Video & Audio References
- **Audio & Speech Analysis**: Use the file at `audio_path` to transcribe spoken dialogue, analyze delivery, hook phrasing, pacing, or identify background audio.
- **Visual & Video Analysis**: Use the file at `video_path` to analyze visual cuts, on-screen text, gestures, and scene composition.
- **Metadata Context**: Leverage `views`, `likes`, `author`, and `caption` to evaluate audience reception, viral performance, and context.

---

## 🔐 Instagram Account Connection

Instagram frequently restricts content behind login walls. To enable automatic downloads:

1. **One-Time Browser Login (Recommended)**:
   Ask the user to run:
   ```bash
   python cli.py login --browser
   ```
   A visible Chromium browser opens. The user logs into Instagram once, and the session is permanently preserved in `./browser_data`. All subsequent downloads by the agent run completely headless.

2. **Cookie Import (Headless / Server Environments)**:
   The user can export `sessionid` and `csrftoken` from browser DevTools:
   ```bash
   python cli.py login --cookies <sessionid> <csrftoken>
   ```

3. **Status Check**:
   The agent can verify whether an Instagram account is connected at any time:
   ```bash
   python cli.py status --json
   ```

---

## 📺 YouTube Support (Shorts & Long-Form)

YouTube downloads require no login. Supported formats:
- YouTube Shorts: `https://www.youtube.com/shorts/<id>`
- Standard Videos: `https://www.youtube.com/watch?v=<id>`
- Shortened URLs: `https://youtu.be/<id>`

Both 1080p/720p `.mp4` video and crystal-clear `.mp3` audio are saved automatically.

---

## ⚡ Filtering Options

Agents or users can filter downloads to save time and bandwidth:
- `--max-duration <seconds>`: Skip videos longer than specified duration (e.g. `--max-duration 30`).
- `--min-views <count>`: Only download viral videos (e.g. `--min-views 100k` or `--min-views 1M`).

---

## 🛠️ Error Handling Runbook

- **Rate Limit / 429 Warning**: The browser engine automatically throttles and introduces human-like jitter. If blocked, wait a few minutes or switch accounts.
- **Private Reel**: If the URL belongs to a private profile that the connected account does not follow, notify the user.
- **FFmpeg Missing**: FFmpeg is required for merging YouTube streams and audio extraction. Ensure `ffmpeg` is available on the system PATH.
