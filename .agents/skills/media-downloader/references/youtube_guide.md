# YouTube Shorts & Video Downloader Guide

The Media Downloader skill provides native support for downloading YouTube Shorts, standard videos, and audio tracks via `yt-dlp` and `FFmpeg`.

---

## 🚀 Capabilities

- **Zero-Login Operation**: Most public YouTube Shorts and long-form videos download immediately without requiring an account.
- **Unified Streams**: Automatically combines the highest-resolution video track and the highest-bitrate audio track into a single, playable `.mp4` file.
- **Automatic Audio Extraction**: Simultaneously produces a high-quality `.mp3` or `.wav` reference track for AI speech-to-text models.
- **Shorts Detection**: Automatically identifies YouTube Shorts (`/shorts/`) and flags `media_type: "short"` in the metadata JSON.

---

## 🔗 Supported URL Patterns

- YouTube Shorts:
  - `https://www.youtube.com/shorts/<SHORT_ID>`
  - `https://m.youtube.com/shorts/<SHORT_ID>`
- Standard Videos:
  - `https://www.youtube.com/watch?v=<VIDEO_ID>`
  - `https://youtu.be/<VIDEO_ID>`
  - `https://www.youtube.com/embed/<VIDEO_ID>`

---

## ⚡ Examples

### Download Short with Audio Reference
```bash
python cli.py download "https://www.youtube.com/shorts/<SHORT_ID>" --audio --json
```

### Download Long Video with Maximum Duration Filter
```bash
python cli.py download "https://www.youtube.com/watch?v=<VIDEO_ID>" --max-duration 300
```

### Custom Output Directory
```bash
python cli.py download "https://www.youtube.com/watch?v=<VIDEO_ID>" --output-dir "./downloads/custom"
```
