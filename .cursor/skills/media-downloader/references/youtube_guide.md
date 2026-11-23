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
  - `https://www.youtube.com/shorts/5X7nDeP6_wQ`
  - `https://m.youtube.com/shorts/5X7nDeP6_wQ`
- Standard Videos:
  - `https://www.youtube.com/watch?v=dQw4w9WgXcQ`
  - `https://youtu.be/dQw4w9WgXcQ`
  - `https://www.youtube.com/embed/dQw4w9WgXcQ`

---

## ⚡ Examples

### Download Short with Audio Reference
```bash
python cli.py download "https://www.youtube.com/shorts/5X7nDeP6_wQ" --audio --json
```

### Download Long Video with Maximum Duration Filter
```bash
python cli.py download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --max-duration 300
```

### Custom Output Directory
```bash
python cli.py download "https://www.youtube.com/watch?v=dQw4w9WgXcQ" --output-dir "./my_research"
```
