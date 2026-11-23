"""
Media Downloader Core Engine
============================
Unified downloader orchestrator for AI agents and CLI users.
Supports:
  - Instagram Reels and Posts (Playwright Browser Engine + yt-dlp fallback)
  - YouTube Shorts and Long-Form Videos (yt-dlp + FFmpeg)
  - Automatic High-Quality MP3/WAV Audio Extraction for AI transcription & reference
  - Structured JSON machine output for AI agents (Cursor, Claude, Codex, Antigravity)
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

# Ensure UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = SCRIPT_DIR / "config.json"
SESSIONS_DIR = SCRIPT_DIR / "sessions"
BROWSER_DATA_DIR = SCRIPT_DIR / "browser_data"


def load_config() -> dict:
    """Load configuration from config.json with robust defaults."""
    defaults = {
        "output_directory": "./downloads",
        "instagram_output_directory": "./downloads/instagram",
        "youtube_output_directory": "./downloads/youtube",
        "extract_audio": True,
        "audio_format": "mp3",
        "save_metadata": True,
        "max_duration_seconds": None,
        "min_views": None,
        "browser_headless": True,
        "browser_data_dir": "./browser_data",
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                defaults.update(json.load(f))
        except Exception as e:
            print(f"⚠️ Warning: Could not read config.json: {e}", file=sys.stderr)
    return defaults


def parse_views_str(val: Any) -> Optional[int]:
    """Parse views string into integer count (e.g. '100k', '1.5M', '50,000')."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return int(val)
    if isinstance(val, str):
        v = val.strip().replace(",", "")
        m = re.search(r"([\d.]+)\s*([kKmMbB]?)", v)
        if m:
            num = float(m.group(1))
            suffix = m.group(2).upper()
            if suffix == "K":
                return int(num * 1_000)
            elif suffix == "M":
                return int(num * 1_000_000)
            elif suffix == "B":
                return int(num * 1_000_000_000)
            return int(num)
    return None


def is_instagram_url(url: str) -> bool:
    """Check if the given URL is an Instagram post or reel."""
    cleaned = url.strip()
    if re.search(r"(?:https?://)?(?:www\.)?instagram\.com/(?:reel|reels|p|tv)/([a-zA-Z0-9_-]+)", cleaned, re.IGNORECASE):
        return True
    if re.search(r"(?:https?://)?(?:www\.)?instagr\.am/(?:reel|reels|p|tv)/([a-zA-Z0-9_-]+)", cleaned, re.IGNORECASE):
        return True
    # Raw shortcode check (typical 11-char alphanumeric)
    if re.fullmatch(r"[a-zA-Z0-9_-]{11}", cleaned) and not is_youtube_url(cleaned):
        return True
    return False


def is_youtube_url(url: str) -> bool:
    """Check if the given URL is a YouTube video or short."""
    cleaned = url.strip()
    patterns = [
        r"(?:https?://)?(?:www\.|m\.)?youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})",
        r"(?:https?://)?(?:www\.|m\.)?youtube\.com/shorts/([a-zA-Z0-9_-]{11})",
        r"(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})",
        r"(?:https?://)?(?:www\.|m\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})",
    ]
    return any(re.search(p, cleaned, re.IGNORECASE) for p in patterns)


def detect_platform(url: str) -> str:
    """Detect platform from URL: 'instagram', 'youtube', or 'unknown'."""
    if is_youtube_url(url):
        return "youtube"
    if is_instagram_url(url):
        return "instagram"
    return "unknown"


def extract_audio_from_file(
    video_path: Union[str, Path],
    audio_path: Optional[Union[str, Path]] = None,
    format: str = "mp3",
) -> Optional[Path]:
    """
    Extract audio track from video file using FFmpeg.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        print(f"❌ Video file does not exist: {video_path}", file=sys.stderr)
        return None

    if audio_path is None:
        audio_path = video_path.with_suffix(f".{format}")
    else:
        audio_path = Path(audio_path)

    audio_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i", str(video_path),
        "-vn",
    ]
    if format == "mp3":
        cmd.extend(["-c:a", "libmp3lame", "-q:a", "2"])
    elif format == "wav":
        cmd.extend(["-c:a", "pcm_s16le"])
    else:
        cmd.extend(["-c:a", "copy"])
    cmd.append(str(audio_path))

    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode == 0 and audio_path.exists():
            return audio_path
        else:
            print(f"⚠️ FFmpeg audio extraction error: {proc.stderr[:300]}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"⚠️ Could not execute FFmpeg for audio extraction: {e}", file=sys.stderr)
        return None


def download_instagram(
    url: str,
    output_dir: Optional[Union[str, Path]] = None,
    extract_audio: bool = True,
    audio_format: str = "mp3",
    max_duration: Optional[float] = None,
    min_views: Optional[Union[int, str]] = None,
    headless: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Download an Instagram Reel or post video.
    Primary engine: Playwright Browser Engine (uses persistent session in browser_data).
    Fallback engine: yt-dlp.
    """
    config = load_config()
    target_dir = Path(output_dir) if output_dir else SCRIPT_DIR / config.get("instagram_output_directory", "./downloads/instagram")
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Primary: Try Playwright Engine
    try:
        from browser_engine import download_single_reel_by_url
        res = download_single_reel_by_url(
            reel_url=url,
            output_dir=target_dir,
            max_duration=max_duration,
            min_views=min_views,
            headless=headless,
            return_info=True,
            extract_audio=extract_audio,
            audio_format=audio_format,
        )
        if isinstance(res, dict) and res.get("status") == "success":
            return res
        elif isinstance(res, dict) and res.get("status") == "skipped":
            return res
    except Exception as e:
        print(f"⚠️ Playwright engine encounter: {e}. Trying yt-dlp fallback...", file=sys.stderr)

    # 2. Fallback: yt-dlp
    try:
        import yt_dlp
        print(f"🔄 Using yt-dlp fallback for Instagram: {url}")
        ydl_opts: Dict[str, Any] = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "outtmpl": str(target_dir / "%(id)s.%(ext)s"),
            "merge_output_format": "mp4",
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            video_id = info.get("id") or "reel"
            mp4_file = target_dir / f"{video_id}.mp4"
            if not mp4_file.exists():
                # check possible glob
                candidates = list(target_dir.glob(f"{video_id}*.mp4"))
                if candidates:
                    mp4_file = candidates[0]

            audio_file = None
            if extract_audio and mp4_file.exists():
                audio_file = extract_audio_from_file(mp4_file, format=audio_format)

            meta_file = target_dir / f"{video_id}_meta.json"
            meta = {
                "id": video_id,
                "url": url,
                "title": info.get("title", ""),
                "description": info.get("description", ""),
                "author": info.get("uploader", ""),
                "views": info.get("view_count"),
                "likes": info.get("like_count"),
                "duration_seconds": info.get("duration"),
                "downloaded_at": datetime.now().isoformat(),
            }
            with open(meta_file, "w", encoding="utf-8") as mf:
                json.dump(meta, mf, indent=2, ensure_ascii=False)

            return {
                "status": "success",
                "platform": "instagram",
                "media_type": "reel",
                "shortcode": video_id,
                "url": url,
                "video_path": str(mp4_file.resolve()),
                "audio_path": str(audio_file.resolve()) if audio_file and audio_file.exists() else None,
                "metadata_path": str(meta_file.resolve()),
                "duration_seconds": info.get("duration"),
                "views": info.get("view_count"),
                "likes": info.get("like_count"),
                "author": info.get("uploader", ""),
                "caption": info.get("description") or info.get("title", ""),
            }
    except Exception as e:
        return {
            "status": "error",
            "platform": "instagram",
            "url": url,
            "error": f"Failed to download Instagram reel: {str(e)}",
        }


def download_youtube(
    url: str,
    output_dir: Optional[Union[str, Path]] = None,
    extract_audio: bool = True,
    audio_format: str = "mp3",
    max_duration: Optional[float] = None,
    min_views: Optional[Union[int, str]] = None,
) -> Dict[str, Any]:
    """
    Download a YouTube Short or Long-Form Video using yt-dlp and FFmpeg.
    """
    import yt_dlp

    config = load_config()
    target_dir = Path(output_dir) if output_dir else SCRIPT_DIR / config.get("youtube_output_directory", "./downloads/youtube")
    target_dir.mkdir(parents=True, exist_ok=True)

    is_short = "/shorts/" in url.lower()
    min_views_num = parse_views_str(min_views)

    # 1. Pre-fetch metadata to perform filtering before downloading
    pre_opts: Dict[str, Any] = {
        "quiet": True,
        "skip_download": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(pre_opts) as ydl:
            meta = ydl.extract_info(url, download=False)
    except Exception as e:
        return {
            "status": "error",
            "platform": "youtube",
            "url": url,
            "error": f"Failed to extract YouTube metadata: {str(e)}",
        }

    video_id = meta.get("id") or "video"
    title = meta.get("title", "")
    duration = meta.get("duration")
    views = meta.get("view_count")
    likes = meta.get("like_count")
    uploader = meta.get("uploader") or meta.get("channel", "")
    description = meta.get("description", "")

    # Check duration filter
    if max_duration is not None and duration is not None and duration > max_duration:
        print(f"⏭️ Skipping YouTube video {video_id}: duration ({duration:.1f}s) > max duration ({max_duration:.1f}s)")
        return {
            "status": "skipped",
            "platform": "youtube",
            "video_id": video_id,
            "reason": f"duration ({duration:.1f}s) > max duration ({max_duration:.1f}s)",
        }

    # Check min views filter
    if min_views_num is not None and views is not None and views < min_views_num:
        print(f"⏭️ Skipping YouTube video {video_id}: views ({views:,}) < min views ({min_views_num:,})")
        return {
            "status": "skipped",
            "platform": "youtube",
            "video_id": video_id,
            "reason": f"views ({views:,}) < min views ({min_views_num:,})",
        }

    print(f"\n{'='*60}")
    print(f"  🎬 YouTube Downloader ({'Short' if is_short else 'Video'})")
    print(f"  🔗 URL: {url}")
    print(f"  🏷️ ID: {video_id}")
    print(f"  📌 Title: {title}")
    if duration is not None:
        print(f"  ⏱️ Duration: {duration:.1f}s")
    if views is not None:
        print(f"  👁️ Views: {views:,}")
    print(f"  📁 Output Directory: {target_dir.resolve()}")
    print(f"{'='*60}\n")

    # 2. Download video
    mp4_file = target_dir / f"{video_id}.mp4"
    ydl_opts: Dict[str, Any] = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(target_dir / f"{video_id}.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as e:
        return {
            "status": "error",
            "platform": "youtube",
            "url": url,
            "error": f"Failed to download YouTube video stream: {str(e)}",
        }

    if not mp4_file.exists():
        candidates = list(target_dir.glob(f"{video_id}*.mp4"))
        if candidates:
            mp4_file = candidates[0]

    if not mp4_file.exists():
        return {
            "status": "error",
            "platform": "youtube",
            "url": url,
            "error": f"Expected video file was not found after download: {mp4_file}",
        }

    file_size_mb = mp4_file.stat().st_size / (1024 * 1024)
    print(f"\n✅ Successfully downloaded: {mp4_file.resolve()} ({file_size_mb:.2f} MB)")

    # 3. Extract audio
    audio_path_obj = None
    if extract_audio:
        audio_file = target_dir / f"{video_id}.{audio_format}"
        audio_path_obj = extract_audio_from_file(mp4_file, audio_file, format=audio_format)
        if audio_path_obj and audio_path_obj.exists():
            print(f"🎵 Saved audio reference: {audio_path_obj.resolve()}")

    # 4. Save metadata JSON
    meta_file = target_dir / f"{video_id}_meta.json"
    meta_dict = {
        "video_id": video_id,
        "url": url,
        "title": title,
        "is_short": is_short,
        "duration_seconds": duration,
        "views": views,
        "likes": likes,
        "author": uploader,
        "description": description,
        "tags": meta.get("tags", []),
        "upload_date": meta.get("upload_date"),
        "downloaded_at": datetime.now().isoformat(),
    }
    with open(meta_file, "w", encoding="utf-8") as mf:
        json.dump(meta_dict, mf, indent=2, ensure_ascii=False)
    print(f"📄 Saved metadata: {meta_file.resolve()}")

    return {
        "status": "success",
        "platform": "youtube",
        "media_type": "short" if is_short else "video",
        "video_id": video_id,
        "url": url,
        "video_path": str(mp4_file.resolve()),
        "audio_path": str(audio_path_obj.resolve()) if audio_path_obj else None,
        "metadata_path": str(meta_file.resolve()),
        "duration_seconds": duration,
        "views": views,
        "likes": likes,
        "author": uploader,
        "title": title,
        "description": description,
    }


def download_media(
    url: str,
    output_dir: Optional[Union[str, Path]] = None,
    extract_audio: Optional[bool] = None,
    audio_format: Optional[str] = None,
    max_duration: Optional[float] = None,
    min_views: Optional[Union[int, str]] = None,
    headless: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Unified entry point for downloading media given any supported link.
    Automatically identifies whether it is an Instagram Reel or YouTube video/short.
    """
    config = load_config()
    should_extract_audio = config.get("extract_audio", True) if extract_audio is None else extract_audio
    fmt = audio_format or config.get("audio_format", "mp3")

    platform = detect_platform(url)

    if platform == "youtube":
        return download_youtube(
            url=url,
            output_dir=output_dir,
            extract_audio=should_extract_audio,
            audio_format=fmt,
            max_duration=max_duration,
            min_views=min_views,
        )
    elif platform == "instagram":
        return download_instagram(
            url=url,
            output_dir=output_dir,
            extract_audio=should_extract_audio,
            audio_format=fmt,
            max_duration=max_duration,
            min_views=min_views,
            headless=headless,
        )
    else:
        # Try generic yt-dlp for any other video platform
        try:
            return download_youtube(
                url=url,
                output_dir=output_dir,
                extract_audio=should_extract_audio,
                audio_format=fmt,
                max_duration=max_duration,
                min_views=min_views,
            )
        except Exception as e:
            return {
                "status": "error",
                "url": url,
                "error": f"Unsupported or unrecognizable video URL format: {url}. (Details: {e})",
            }


def get_system_status() -> Dict[str, Any]:
    """
    Diagnose system status, Instagram login state, Playwright, FFmpeg, and yt-dlp readiness.
    """
    # 1. Instagram login detection
    has_browser_data = BROWSER_DATA_DIR.exists() and any(BROWSER_DATA_DIR.iterdir())
    has_saved_session = SESSIONS_DIR.exists() and any(SESSIONS_DIR.glob("*_session"))
    instagram_connected = has_browser_data or has_saved_session

    saved_accounts = []
    if SESSIONS_DIR.exists():
        saved_accounts = [p.stem.replace("_session", "") for p in SESSIONS_DIR.glob("*_session")]

    # 2. FFmpeg detection
    ffmpeg_path = shutil.which("ffmpeg")
    ffmpeg_ok = ffmpeg_path is not None

    # 3. yt-dlp detection
    ytdlp_version = None
    try:
        import yt_dlp.version
        ytdlp_version = yt_dlp.version.__version__
    except Exception:
        pass

    # 4. Playwright detection
    playwright_ok = False
    try:
        import playwright
        playwright_ok = True
    except Exception:
        pass

    # 5. Downloads stats
    downloads_dir = SCRIPT_DIR / "downloads"
    total_videos = 0
    total_audio = 0
    total_size_bytes = 0
    if downloads_dir.exists():
        for p in downloads_dir.rglob("*"):
            if p.is_file():
                total_size_bytes += p.stat().st_size
                if p.suffix.lower() in [".mp4", ".webm", ".mkv"]:
                    total_videos += 1
                elif p.suffix.lower() in [".mp3", ".wav", ".m4a"]:
                    total_audio += 1

    return {
        "status": "ok",
        "instagram": {
            "connected": instagram_connected,
            "has_browser_profile": has_browser_data,
            "saved_sessions": saved_accounts,
            "browser_data_dir": str(BROWSER_DATA_DIR.resolve()),
        },
        "tools": {
            "ffmpeg": {
                "installed": ffmpeg_ok,
                "path": ffmpeg_path,
            },
            "yt_dlp": {
                "installed": ytdlp_version is not None,
                "version": ytdlp_version,
            },
            "playwright": {
                "installed": playwright_ok,
            },
        },
        "storage": {
            "downloads_dir": str(downloads_dir.resolve()),
            "total_videos": total_videos,
            "total_audio": total_audio,
            "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
        },
    }
