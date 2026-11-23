"""
Instagram Reels Downloader — Ban-Safe Edition
==============================================
Downloads all reels from a public Instagram profile with aggressive
anti-ban protections: randomized delays, batch pausing, automatic 429
recovery, resume support, and session-cookie authentication.

Usage:
    python downloader.py --login YOUR_USERNAME          # One-time login
    python downloader.py --username TARGET_ACCOUNT      # Download reels
    python downloader.py --username TARGET_ACCOUNT --resume  # Resume interrupted download
"""

import argparse
import getpass
import hashlib
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Union

from browser_engine import ProgressTracker, parse_views_str

# Fix Windows console encoding for emoji/unicode output
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

try:
    import instaloader
except ImportError:
    print("ERROR: 'instaloader' is not installed.")
    print("Run: pip install -r requirements.txt")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = SCRIPT_DIR / "config.json"
SESSIONS_DIR = SCRIPT_DIR / "sessions"
PROGRESS_DIR = SCRIPT_DIR / "progress"


# ---------------------------------------------------------------------------
# Custom Rate Controller — the core of ban-safety
# ---------------------------------------------------------------------------
class BanSafeRateController(instaloader.RateController):
    """
    Overrides instaloader's default rate controller to inject randomized,
    human-like delays between every API request. This is the single most
    important layer of protection against Instagram's anti-bot detection.
    """

    def __init__(self, context, min_delay: float = 2.0, max_delay: float = 6.0):
        super().__init__(context)
        self.min_delay = min_delay
        self.max_delay = max_delay

    def sleep(self, secs: float):
        """
        Called by instaloader before each request. We override this to add
        a random jitter on top of the requested sleep, so the request pattern
        looks organic rather than mechanical.
        """
        jitter = random.uniform(self.min_delay, self.max_delay)
        total = secs + jitter
        time.sleep(total)

    def handle_429(self, query_type: str) -> None:
        """
        Called when Instagram returns HTTP 429 (Too Many Requests).
        We back off aggressively to avoid escalation to a permanent ban.
        """
        wait = random.uniform(5 * 60, 15 * 60)  # 5-15 minutes
        print(f"\n⚠️  Rate limited (429)! Backing off for {wait / 60:.1f} minutes...")
        print(f"    Will resume at {datetime.now() + timedelta(seconds=wait):%H:%M:%S}")
        time.sleep(wait)


# ---------------------------------------------------------------------------
# Configuration Loader
# ---------------------------------------------------------------------------
def load_config() -> dict:
    """Load configuration from config.json with sensible defaults."""
    defaults = {
        "min_delay_seconds": 30,
        "max_delay_seconds": 90,
        "batch_size": 5,
        "batch_pause_minutes": 3,
        "max_downloads_per_session": 100,
        "output_directory": "./downloads",
        "save_metadata": True,
        "max_duration_seconds": None,
        "min_views": None,
        "on_429_wait_minutes": 10,
        "max_retries_on_error": 3,
        "cooldown_after_error_seconds": 120,
    }

    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                user_config = json.load(f)
            defaults.update(user_config)
            print(f"✅ Loaded config from {CONFIG_PATH}")
        except (json.JSONDecodeError, IOError) as e:
            print(f"⚠️  Failed to load config.json ({e}), using defaults.")

    return defaults


# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------
def login_and_save_session(username: str):
    """
    Logs in to Instagram and saves the session cookie to a local file.
    This only needs to be done once; subsequent runs load the saved session.
    """
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    loader = instaloader.Instaloader()
    password = getpass.getpass(f"Enter password for @{username}: ")

    try:
        loader.login(username, password)
        loader.save_session_to_file(str(SESSIONS_DIR / f"{username}_session"))
        print(f"\n✅ Session saved! You can now run downloads without re-entering your password.")
        print(f"   Session file: {SESSIONS_DIR / f'{username}_session'}")
    except instaloader.exceptions.BadCredentialsException:
        print("❌ Login failed: incorrect username or password.")
        sys.exit(1)
    except instaloader.exceptions.TwoFactorAuthRequiredException:
        print("❌ Two-factor authentication is enabled on this account.")
        print("   Please disable 2FA on your throwaway account, or use browser cookie import.")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Login failed: {e}")
        sys.exit(1)


def save_session_from_cookies(username: str, sessionid: str, csrftoken: str, ds_user_id: str = ""):
    """
    Saves a session using cookies exported from a web browser.
    Completely bypasses Instagram CLI login checkpoints and 2FA prompts.
    """
    import pickle
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    cookies = {
        "sessionid": sessionid.strip(),
        "csrftoken": csrftoken.strip(),
    }
    if ds_user_id:
        cookies["ds_user_id"] = ds_user_id.strip()

    session_file = SESSIONS_DIR / f"{username}_session"
    with open(session_file, "wb") as f:
        pickle.dump(cookies, f)

    # Verify session
    loader = instaloader.Instaloader()
    try:
        loader.load_session_from_file(username, str(session_file))
        print(f"\n✅ Session successfully created from cookies for @{username}!")
        print(f"   Saved to: {session_file}")
    except Exception as e:
        print(f"⚠️  Cookies saved, but test load showed: {e}")



def load_session(loader: instaloader.Instaloader, username: str) -> bool:
    """Load a previously saved session. Returns True on success."""
    session_file = SESSIONS_DIR / f"{username}_session"
    if not session_file.exists():
        return False
    try:
        loader.load_session_from_file(username, str(session_file))
        print(f"✅ Session loaded for @{username}")
        return True
    except Exception as e:
        print(f"⚠️  Failed to load session ({e}). Please re-login with --login {username}")
        return False


# ---------------------------------------------------------------------------
# Reel Metadata Saver
# ---------------------------------------------------------------------------
def save_reel_metadata(post, output_dir: Path):
    """Save reel metadata (caption, date, likes, views, duration) alongside the video."""
    meta = {
        "shortcode": post.shortcode,
        "url": f"https://www.instagram.com/reel/{post.shortcode}/",
        "duration_seconds": post.video_duration if hasattr(post, "video_duration") else None,
        "views": getattr(post, "video_view_count", None),
        "date": post.date_utc.isoformat() if post.date_utc else None,
        "caption": post.caption or "",
        "likes": post.likes,
        "downloaded_at": datetime.now().isoformat(),
    }
    meta_file = output_dir / f"{post.shortcode}_meta.json"
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main Download Engine
# ---------------------------------------------------------------------------
def download_reels(
    login_username: str,
    target_username: str,
    resume: bool = False,
    max_duration: Optional[float] = None,
    min_views: Optional[Union[int, str]] = None,
):
    """
    Core download function with full ban-safety measures:
    1. Randomized delays between each download (30-90s default)
    2. Batch pausing (every N reels, pause for several minutes)
    3. Automatic 429 recovery with long backoff
    4. Resume from progress file on interruption
    5. Session limit (max downloads per run)
    6. Max duration filtering
    7. Min views filtering
    """
    config = load_config()
    if max_duration is None:
        max_duration = config.get("max_duration_seconds")
    if min_views is None:
        min_views = parse_views_str(config.get("min_views"))
    elif isinstance(min_views, str):
        min_views = parse_views_str(min_views)

    # --- Initialize Instaloader with ban-safe rate controller ---
    rate_ctrl = lambda ctx: BanSafeRateController(
        ctx,
        min_delay=2.0,  # Small per-request jitter (on top of our main delays)
        max_delay=5.0,
    )

    loader = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,  # We handle metadata ourselves
        compress_json=False,
        post_metadata_txt_pattern="",
        rate_controller=rate_ctrl,
    )

    # --- Load session ---
    if not load_session(loader, login_username):
        print(f"❌ No session found for @{login_username}.")
        print(f"   Run: python downloader.py --login {login_username}")
        sys.exit(1)

    # --- Setup output directory ---
    output_dir = Path(config["output_directory"]) / target_username
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"📁 Output directory: {output_dir.resolve()}")

    # --- Setup progress tracker (persistent across runs) ---
    tracker = ProgressTracker(target_username)
    if tracker.count > 0:
        print(f"🔄 Progress tracker loaded: {tracker.count} reels previously recorded for @{target_username}.")

    # --- Fetch profile ---
    try:
        print(f"\n🔍 Fetching profile: @{target_username}...")
        profile = instaloader.Profile.from_username(loader.context, target_username)
        print(f"   📊 {profile.mediacount} total posts | {profile.followers} followers")
    except instaloader.exceptions.ProfileNotExistsException:
        print(f"❌ Profile @{target_username} does not exist.")
        sys.exit(1)
    except instaloader.exceptions.LoginRequiredException:
        print("❌ Login required. Your session may have expired.")
        print(f"   Run: python downloader.py --login {login_username}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to fetch profile: {e}")
        sys.exit(1)

    # --- Download loop with ban-safety ---
    downloaded_this_session = 0
    skipped = 0
    errors = 0
    batch_counter = 0
    max_per_session = config["max_downloads_per_session"]
    batch_size = config["batch_size"]
    min_delay = config["min_delay_seconds"]
    max_delay = config["max_delay_seconds"]
    batch_pause = config["batch_pause_minutes"] * 60
    max_retries = config["max_retries_on_error"]
    cooldown_on_error = config["cooldown_after_error_seconds"]

    print(f"\n{'='*60}")
    print(f"  🚀 Starting download — Ban-Safe Mode")
    print(f"  ⏱️  Delay between reels: {min_delay}-{max_delay}s (randomized)")
    print(f"  📦 Batch size: {batch_size} reels, then {config['batch_pause_minutes']}min pause")
    print(f"  🔒 Max per session: {max_per_session} reels")
    if min_views is not None:
        print(f"  👁️  Min Views: >= {min_views:,} (reels with fewer views will be skipped)")
    if max_duration is not None:
        print(f"  ⏱️  Max Duration: <= {max_duration:.1f}s (reels longer will be skipped)")
    print(f"{'='*60}\n")

    try:
        for post in profile.get_posts():
            # --- Session limit check ---
            if downloaded_this_session >= max_per_session:
                print(f"\n🛑 Session limit reached ({max_per_session} reels).")
                print(f"   Run again with --resume to continue safely.")
                break

            # --- Filter: only videos/reels ---
            if not post.is_video:
                continue

            reel_url = f"https://www.instagram.com/reel/{post.shortcode}/"

            # --- Filter: min views ---
            views = getattr(post, "video_view_count", None)
            if min_views is not None and views is not None and views < min_views:
                print(f"⏭️  Skipping reel {post.shortcode}: views ({views:,}) < min ({min_views:,})")
                skipped += 1
                continue

            # --- Filter: max duration ---
            if max_duration is not None and post.video_duration:
                if post.video_duration > max_duration:
                    print(f"⏭️  Skipping reel {post.shortcode}: duration ({post.video_duration:.1f}s) > max ({max_duration:.1f}s)")
                    skipped += 1
                    continue

            # --- Skip already downloaded ---
            if tracker.is_downloaded(post.shortcode, reel_url):
                skipped += 1
                continue

            # --- Download with retry logic ---
            success = False
            for attempt in range(1, max_retries + 1):
                try:
                    views_str = f" [👁️ {views:,} views]" if views is not None else ""
                    print(
                        f"📥 [{downloaded_this_session + 1}/{max_per_session}] "
                        f"Downloading reel: {post.shortcode}{views_str} "
                        f"({post.date_utc.strftime('%Y-%m-%d') if post.date_utc else 'unknown date'})"
                    )
                    loader.download_post(post, target=str(output_dir))

                    meta = {
                        "shortcode": post.shortcode,
                        "url": reel_url,
                        "duration_seconds": getattr(post, "video_duration", None),
                        "views": views,
                        "caption": post.caption or "",
                        "date": post.date_utc.isoformat() if post.date_utc else None,
                        "likes": post.likes,
                        "downloaded_at": datetime.now().isoformat(),
                    }

                    # Save metadata if enabled
                    if config["save_metadata"]:
                        save_reel_metadata(post, output_dir)

                    tracker.mark_downloaded(post.shortcode, reel_url, meta)
                    downloaded_this_session += 1
                    batch_counter += 1
                    success = True
                    break

                except instaloader.exceptions.ConnectionException as e:
                    error_str = str(e).lower()
                    if "429" in error_str or "too many" in error_str:
                        wait_mins = config["on_429_wait_minutes"]
                        wait_secs = wait_mins * 60 + random.uniform(30, 120)
                        print(f"\n⚠️  429 Rate Limited! (attempt {attempt}/{max_retries})")
                        print(f"   Cooling down for ~{wait_secs / 60:.1f} minutes...")
                        print(f"   Resume at: {datetime.now() + timedelta(seconds=wait_secs):%H:%M:%S}")
                        time.sleep(wait_secs)
                    else:
                        print(f"   ⚠️  Connection error (attempt {attempt}/{max_retries}): {e}")
                        time.sleep(cooldown_on_error)

                except Exception as e:
                    print(f"   ❌ Error (attempt {attempt}/{max_retries}): {e}")
                    time.sleep(cooldown_on_error)

            if not success:
                errors += 1
                print(f"   ❌ Skipping reel {post.shortcode} after {max_retries} failed attempts.")

            # --- Batch pause: extra long break every N reels ---
            if batch_counter >= batch_size:
                batch_counter = 0
                jittered_pause = batch_pause + random.uniform(-30, 60)
                print(
                    f"\n⏸️  Batch complete ({batch_size} reels). "
                    f"Pausing for {jittered_pause / 60:.1f} minutes to stay safe..."
                )
                print(f"   Resume at: {datetime.now() + timedelta(seconds=jittered_pause):%H:%M:%S}")
                time.sleep(jittered_pause)
                print("   ▶️  Resuming downloads...\n")

            # --- Random delay between individual reels ---
            else:
                delay = random.uniform(min_delay, max_delay)
                print(f"   ⏱️  Waiting {delay:.0f}s before next reel...")
                time.sleep(delay)

    except KeyboardInterrupt:
        print(f"\n\n⛔ Interrupted by user. Progress saved — use --resume to continue.")

    # --- Final Summary ---
    print(f"\n{'='*60}")
    print(f"  ✅ Download Summary")
    print(f"  📥 Downloaded this session: {downloaded_this_session}")
    print(f"  ⏭️  Skipped (already had):  {skipped}")
    print(f"  ❌ Errors:                  {errors}")
    print(f"  💾 Total in progress file:  {tracker.count}")
    print(f"  📁 Saved to: {output_dir.resolve()}")
    print(f"{'='*60}")

    if downloaded_this_session >= max_per_session:
        print(f"\n💡 Tip: You hit the session limit. Wait a few hours, then run again:")
        print(f"   python downloader.py --username {target_username} --resume")


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="📥 Instagram Reels Downloader — Ban-Safe Edition",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python downloader.py --login my_throwaway_account
  python downloader.py --username target_profile --login-as my_throwaway_account
  python downloader.py --username target_profile --login-as my_throwaway_account --resume
        """,
    )

    parser.add_argument(
        "--login",
        metavar="USERNAME",
        help="Login to Instagram and save session (one-time setup)",
    )
    parser.add_argument(
        "--import-cookies",
        metavar="USERNAME",
        help="Interactively import session cookies (sessionid, csrftoken) from your browser",
    )
    parser.add_argument(
        "--username",
        metavar="TARGET",
        help="Instagram username whose reels you want to download",
    )
    parser.add_argument(
        "--url",
        "--link",
        dest="url",
        metavar="URL",
        help="Download a single reel directly by its Instagram link (e.g. https://www.instagram.com/reel/C8.../)",
    )
    parser.add_argument(
        "--login-as",
        metavar="USERNAME",
        dest="login_as",
        help="The throwaway account to authenticate with (defaults to the session found in /sessions)",
    )
    parser.add_argument(
        "--engine",
        choices=["api", "browser"],
        default=None,
        help="Download engine: 'browser' (Playwright, default) or 'api' (Instaloader API)",
    )
    parser.add_argument(
        "--browser-login",
        action="store_true",
        help="Open a real browser window to log into Instagram and save persistent session for browser engine",
    )
    parser.add_argument(
        "--browser-visible",
        action="store_true",
        help="Keep browser window visible while running the browser engine",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume a previously interrupted download",
    )
    parser.add_argument(
        "--max-duration",
        type=float,
        metavar="SECONDS",
        help="Only download reels with duration <= max_duration (in seconds). Longer reels are skipped.",
    )
    parser.add_argument(
        "--min-views",
        "--views",
        dest="min_views",
        metavar="VIEWS",
        help="Only download reels with views >= min_views (e.g. 100k, 100000, 1M). Reels with fewer views are skipped.",
    )

    args = parser.parse_args()

    print(r"""
    ╔══════════════════════════════════════════════╗
    ║   📥 Instagram Reels Downloader              ║
    ║   🛡️  Ban-Safe Edition                        ║
    ╚══════════════════════════════════════════════╝
    """)

    # --- Mode: Browser Login ---
    if args.browser_login:
        from browser_engine import browser_login
        browser_login()
        return

    # --- Mode: Login ---
    if args.login:
        login_and_save_session(args.login)
        return

    # --- Mode: Import Cookies ---
    if args.import_cookies:
        u = args.import_cookies
        print(f"🍪 Importing browser cookies for @{u}")
        print("To find these: Open Instagram in your browser -> Press F12 -> Application -> Cookies -> instagram.com")
        sess_id = input("Paste 'sessionid' cookie value: ").strip()
        csrf = input("Paste 'csrftoken' cookie value: ").strip()
        ds_id = input("Paste 'ds_user_id' cookie value (optional, press Enter to skip): ").strip()
        if not sess_id or not csrf:
            print("❌ Both sessionid and csrftoken are required.")
            sys.exit(1)
        save_session_from_cookies(u, sess_id, csrf, ds_id)
        return

    min_views = args.min_views if args.min_views is not None else load_config().get("min_views")
    if min_views is not None:
        min_views = parse_views_str(min_views)

    # --- Mode: Single Reel Download by URL ---
    if args.url:
        engine = args.engine or "browser"
        is_headless = not args.browser_visible if args.browser_visible else None
        max_duration = args.max_duration if args.max_duration is not None else load_config().get("max_duration_seconds")

        if engine == "api":
            from browser_engine import extract_shortcode
            sc = extract_shortcode(args.url)
            if not sc:
                print(f"❌ Invalid reel URL or shortcode: {args.url}")
                sys.exit(1)
            login_user = args.login_as
            if not login_user:
                SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
                sessions = list(SESSIONS_DIR.glob("*_session"))
                if sessions:
                    login_user = sessions[0].stem.replace("_session", "")
            loader = instaloader.Instaloader()
            if login_user:
                load_session(loader, login_user)
            out = Path(load_config()["output_directory"]) / "single_reels"
            out.mkdir(parents=True, exist_ok=True)
            print(f"📥 Downloading single reel via API: {sc}...")
            post = instaloader.Post.from_shortcode(loader.context, sc)
            if min_views is not None and getattr(post, "video_view_count", None):
                if post.video_view_count < min_views:
                    print(f"⏭️ Skipping reel {sc}: views ({post.video_view_count:,}) < min views ({min_views:,})")
                    return
            if max_duration is not None and post.video_duration:
                if post.video_duration > max_duration:
                    print(f"⏭️ Skipping reel {sc}: duration ({post.video_duration:.1f}s) > max duration ({max_duration:.1f}s)")
                    return
            loader.download_post(post, target=str(out))
            print(f"✅ Saved to: {out.resolve()}")
            return
        else:
            from browser_engine import download_single_reel_by_url
            success = download_single_reel_by_url(
                args.url,
                max_duration=max_duration,
                min_views=min_views,
                headless=is_headless,
            )
            sys.exit(0 if success else 1)

    # --- Mode: Profile Reels Download ---
    if args.username:
        engine = args.engine or "browser"
        max_duration = args.max_duration if args.max_duration is not None else load_config().get("max_duration_seconds")

        if engine == "browser":
            from browser_engine import download_reels_browser
            is_headless = not args.browser_visible if args.browser_visible else None
            download_reels_browser(
                args.username,
                resume=args.resume,
                max_duration=max_duration,
                min_views=min_views,
                headless=is_headless,
            )
            return

        # Engine: API (Instaloader)
        login_user = args.login_as

        if not login_user:
            # Auto-detect from sessions directory
            SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
            sessions = list(SESSIONS_DIR.glob("*_session"))
            if sessions:
                login_user = sessions[0].stem.replace("_session", "")
                print(f"🔑 Auto-detected login account: @{login_user}")
            else:
                print("❌ No saved sessions found.")
                print("   First run: python downloader.py --login YOUR_THROWAWAY_USERNAME")
                sys.exit(1)

        download_reels(login_user, args.username, resume=args.resume, max_duration=max_duration, min_views=min_views)
        return

    # --- No arguments: show help ---
    parser.print_help()


if __name__ == "__main__":
    main()
