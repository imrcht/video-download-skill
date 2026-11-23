#!/usr/bin/env python3
"""
Media Downloader Unified CLI
============================
Universal command-line interface for human developers and AI agents.
Supports downloading Instagram Reels and YouTube Shorts / Videos, extracting audio references,
and authenticating Instagram accounts.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

# Ensure UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from media_downloader import (
    download_media,
    get_system_status,
    load_config,
    parse_views_str,
)


def print_banner():
    """Print ASCII banner for interactive CLI usage."""
    print(r"""
 ╔══════════════════════════════════════════════════════════════════╗
 ║  🎬 Media Downloader — Reels, Shorts & Long-Form Video Engine    ║
 ║  🤖 Built for AI Agents & Creators: Video + Audio References     ║
 ║  🛡️  Dual Engine: Playwright Chromium + yt-dlp + FFmpeg          ║
 ╚══════════════════════════════════════════════════════════════════╝
""")


def cmd_download(args):
    """Handle download subcommand."""
    if not args.json:
        print_banner()

    min_views = parse_views_str(args.min_views) if args.min_views else None

    # Determine audio extraction setting
    config = load_config()
    extract_audio = config.get("extract_audio", True)
    if args.audio is True:
        extract_audio = True
    elif args.no_audio is True:
        extract_audio = False

    result = download_media(
        url=args.url,
        output_dir=args.output_dir,
        extract_audio=extract_audio,
        audio_format=args.audio_format,
        max_duration=args.max_duration,
        min_views=min_views,
        headless=not args.browser_visible if args.browser_visible else None,
    )

    if args.json:
        # Machine output for AI agents
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        # Pretty human output
        if result.get("status") == "success":
            print("\n✨ Download Summary:")
            print(f"  • Platform:   {result.get('platform', '').upper()}")
            print(f"  • Video:      {result.get('video_path')}")
            if result.get("audio_path"):
                print(f"  • Audio:      {result.get('audio_path')} (Ready for Whisper/AI)")
            if result.get("metadata_path"):
                print(f"  • Metadata:   {result.get('metadata_path')}")
            if result.get("duration_seconds"):
                print(f"  • Duration:   {result.get('duration_seconds')}s")
            if result.get("views"):
                print(f"  • Views:      {result.get('views'):,}")
            if result.get("likes"):
                print(f"  • Likes:      {result.get('likes'):,}")
            print("\n✅ Finished successfully.")
        elif result.get("status") == "skipped":
            print(f"\n⏭️ Skipped: {result.get('reason')}")
        else:
            print(f"\n❌ Error: {result.get('error', 'Unknown failure')}")
            sys.exit(1)


def cmd_login(args):
    """Handle Instagram login."""
    print_banner()

    if args.browser or (not args.cookies and not args.credentials):
        from browser_engine import browser_login
        print("🌐 Launching interactive browser for Instagram login...")
        browser_login()
        return

    if args.cookies:
        from downloader import save_session_from_cookies
        username = args.username or "instagram_user"
        sess_id = args.cookies[0]
        csrf = args.cookies[1]
        ds_id = args.cookies[2] if len(args.cookies) > 2 else ""
        save_session_from_cookies(username, sess_id, csrf, ds_id)
        return

    if args.credentials:
        from downloader import login_and_save_session
        username = args.credentials
        login_and_save_session(username)
        return


def cmd_status(args):
    """Handle status check."""
    status_info = get_system_status()
    if args.json:
        print(json.dumps(status_info, indent=2, ensure_ascii=False))
        return

    print_banner()
    print("🔍 System Status & Diagnostic Check:\n")

    # Instagram
    ig = status_info["instagram"]
    ig_status = "✅ Connected" if ig["connected"] else "⚠️ Not connected (run: python cli.py login)"
    print(f"Instagram: {ig_status}")
    if ig["has_browser_profile"]:
        print(f"  - Browser Profile: Found at {ig['browser_data_dir']}")
    if ig["saved_sessions"]:
        print(f"  - Saved API Sessions: {', '.join(ig['saved_sessions'])}")

    # Tools
    tools = status_info["tools"]
    ff_status = f"✅ Installed ({tools['ffmpeg']['path']})" if tools["ffmpeg"]["installed"] else "❌ Not found in PATH"
    print(f"\nFFmpeg: {ff_status}")

    yt_status = f"✅ Installed (v{tools['yt_dlp']['version']})" if tools["yt_dlp"]["installed"] else "❌ Not installed"
    print(f"yt-dlp: {yt_status}")

    pw_status = "✅ Installed" if tools["playwright"]["installed"] else "❌ Not installed"
    print(f"Playwright: {pw_status}")

    # Storage
    st = status_info["storage"]
    print(f"\nDownloads Storage ({st['downloads_dir']}):")
    print(f"  - Videos: {st['total_videos']}")
    print(f"  - Audio tracks: {st['total_audio']}")
    print(f"  - Total size: {st['total_size_mb']} MB\n")


def main():
    parser = argparse.ArgumentParser(
        description="Media Downloader — Download Instagram Reels and YouTube Shorts/Videos with Audio for AI Agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Available commands")

    # --- Subcommand: download ---
    p_dl = subparsers.add_parser("download", help="Download a video/reel from Instagram or YouTube")
    p_dl.add_argument("url", help="Instagram reel/post URL or YouTube video/short URL")
    p_dl.add_argument("--output-dir", "-o", help="Custom output directory")
    p_dl.add_argument("--audio", action="store_true", default=None, help="Force extract audio reference track (MP3/WAV)")
    p_dl.add_argument("--no-audio", action="store_true", help="Do not extract audio track")
    p_dl.add_argument("--audio-format", default="mp3", choices=["mp3", "wav"], help="Audio extraction format (default: mp3)")
    p_dl.add_argument("--max-duration", type=float, metavar="SECS", help="Skip videos longer than SECS seconds")
    p_dl.add_argument("--min-views", "--views", metavar="N", help="Skip videos with fewer than N views (e.g. 100k, 1M)")
    p_dl.add_argument("--browser-visible", action="store_true", help="Show browser window during Instagram extraction")
    p_dl.add_argument("--json", action="store_true", help="Output machine-readable JSON (ideal for AI agents)")

    # --- Subcommand: login ---
    p_login = subparsers.add_parser("login", help="Connect an Instagram account")
    p_login.add_argument("--browser", action="store_true", help="Launch visible browser for manual Instagram login (default)")
    p_login.add_argument("--cookies", nargs="+", metavar=("SESSIONID", "CSRFTOKEN"), help="Import session cookies directly (headless)")
    p_login.add_argument("--credentials", metavar="USERNAME", help="Log in via username & password with Instaloader")
    p_login.add_argument("--username", "-u", help="Username associated with imported cookies")

    # --- Subcommand: status ---
    p_status = subparsers.add_parser("status", help="Check system health, Instagram connection, and tools")
    p_status.add_argument("--json", action="store_true", help="Output status in JSON")

    # Fallback support for direct: python cli.py <url>
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-") and sys.argv[1] not in ["download", "login", "status"]:
        # User passed URL directly: python cli.py "https://..."
        sys.argv.insert(1, "download")

    args = parser.parse_args()

    if args.subcommand == "download":
        cmd_download(args)
    elif args.subcommand == "login":
        cmd_login(args)
    elif args.subcommand == "status":
        cmd_status(args)
    else:
        print_banner()
        parser.print_help()


if __name__ == "__main__":
    main()
