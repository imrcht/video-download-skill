"""
Playwright Browser Engine for Instagram Reels Downloader
=========================================================
Bypasses API rate limits, checkpoints, and 'feedback_required' blocks
by using an automated Chromium browser (Playwright) with persistent sessions,
GraphQL response interception, and human-like scroll simulation.
"""

import base64
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Union

import requests
from playwright.sync_api import BrowserContext, Page, sync_playwright

# Fix Windows console encoding for emoji/unicode output
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

SCRIPT_DIR = Path(__file__).parent.resolve()
CONFIG_PATH = SCRIPT_DIR / "config.json"
PROGRESS_DIR = SCRIPT_DIR / "progress"


def load_config() -> dict:
    """Load configuration from config.json with defaults."""
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
        "browser_scroll_delay_ms_min": 2000,
        "browser_scroll_delay_ms_max": 5000,
        "browser_headless": True,
        "browser_data_dir": "./browser_data",
    }
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                defaults.update(json.load(f))
        except Exception as e:
            print(f"⚠️ Failed to read config.json: {e}")
    return defaults


def parse_views_str(val) -> Optional[int]:
    """
    Parse view count from integer or string representation.
    Supports formats like '100k', '1.5M', '31.3K', '100,000', 100000.
    """
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
                return int(num * 1000)
            elif suffix == "M":
                return int(num * 1_000_000)
            elif suffix == "B":
                return int(num * 1_000_000_000)
            return int(num)
    return None


class ProgressTracker:
    """Tracks downloaded shortcodes and URLs to guarantee duplicate prevention across runs."""

    def __init__(self, target_username: str):
        self.target_username = target_username
        PROGRESS_DIR.mkdir(parents=True, exist_ok=True)
        self.progress_file = PROGRESS_DIR / f"{target_username}_progress.json"
        self.data = self._load()

    def _load(self) -> dict:
        if self.progress_file.exists():
            try:
                with open(self.progress_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "downloaded" not in data:
                        data["downloaded"] = []
                    if "downloaded_urls" not in data:
                        data["downloaded_urls"] = [f"https://www.instagram.com/reel/{sc}/" for sc in data["downloaded"]]
                    if "history" not in data:
                        data["history"] = []
                    return data
            except Exception:
                pass
        return {
            "target_username": self.target_username,
            "downloaded": [],
            "downloaded_urls": [],
            "history": [],
            "last_run": None,
            "total_downloaded": 0,
        }

    def save(self):
        self.data["last_run"] = datetime.now().isoformat()
        with open(self.progress_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2)

    def is_downloaded(self, shortcode: str, url: Optional[str] = None) -> bool:
        if shortcode in self.data.get("downloaded", []):
            return True
        if url and url in self.data.get("downloaded_urls", []):
            return True
        return False

    def mark_downloaded(self, shortcode: str, url: Optional[str] = None, meta: Optional[dict] = None):
        if url is None:
            url = f"https://www.instagram.com/reel/{shortcode}/"
        if shortcode not in self.data["downloaded"]:
            self.data["downloaded"].append(shortcode)
        if url not in self.data["downloaded_urls"]:
            self.data["downloaded_urls"].append(url)
        if meta and meta not in self.data["history"]:
            self.data["history"].append(meta)
        self.data["total_downloaded"] = len(self.data["downloaded"])
        self.save()

    @property
    def count(self) -> int:
        return len(self.data["downloaded"])


def browser_login():
    """
    Opens a visible browser window so the user can log into Instagram manually.
    The session is saved in the persistent user data directory.
    """
    config = load_config()
    data_dir = SCRIPT_DIR / config.get("browser_data_dir", "./browser_data")
    data_dir.mkdir(parents=True, exist_ok=True)

    print("\n" + "=" * 60)
    print("  🌐 Instagram Browser Login Setup")
    print("=" * 60)
    print(f"Opening browser using profile folder: {data_dir.resolve()}")
    print("Please log into Instagram in the browser window that appears.\n")

    with sync_playwright() as p:
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ]
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(data_dir),
            headless=False,
            args=args,
            viewport={"width": 1280, "height": 800},
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://www.instagram.com/", wait_until="domcontentloaded")

        print("👉 Complete your login, 2FA, or checkpoint in the opened browser window.")
        input("Press [Enter] here once you are logged in and see your Instagram feed: ")

        # Save cookies & verify
        cookies = context.cookies()
        has_session = any(c.get("name") == "sessionid" for c in cookies)
        if has_session:
            print("✅ Successfully detected active session cookie ('sessionid')!")
        else:
            print("⚠️ 'sessionid' cookie not yet detected. If you logged in, cookies will still be saved in the profile.")

        context.close()
        print(f"✅ Browser session saved to {data_dir.resolve()}.\n")


def extract_duration_from_url(url: str) -> Optional[float]:
    """
    Extract duration in seconds from the progressive video URL query string ('efg' parameter).
    Instagram CDN encodes metadata including 'duration_s' into this base64 parameter.
    """
    if not url:
        return None
    try:
        parsed = urllib.parse.urlparse(url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "efg" in qs:
            efg_val = qs["efg"][0]
            padded = efg_val + "=" * ((4 - len(efg_val) % 4) % 4)
            decoded = base64.b64decode(padded).decode("utf-8", errors="replace")
            data = json.loads(decoded)
            if "duration_s" in data:
                return float(data["duration_s"])
    except Exception:
        pass
    return None


def get_reel_duration(shortcode: str, video_url: Optional[str], captured_reels: dict, page: Optional[Page] = None) -> Optional[float]:
    """Retrieve duration in seconds from captured_reels cache, video URL ('efg'), or DOM element."""
    # 1. From captured_reels cache
    if shortcode in captured_reels and captured_reels[shortcode].get("duration") is not None:
        return float(captured_reels[shortcode]["duration"])

    # 2. From video URL parameter
    if video_url:
        dur = extract_duration_from_url(video_url)
        if dur is not None:
            if shortcode in captured_reels:
                captured_reels[shortcode]["duration"] = dur
            return dur

    # 3. From page DOM if page is active
    if page:
        try:
            dom_dur = page.evaluate("() => { const v = document.querySelector('video'); return v && v.duration ? v.duration : null; }")
            if dom_dur and isinstance(dom_dur, (int, float)) and dom_dur > 0:
                dur = round(float(dom_dur), 2)
                if shortcode in captured_reels:
                    captured_reels[shortcode]["duration"] = dur
                return dur
        except Exception:
            pass

    return None


def extract_reels_from_json(obj, results: Dict[str, dict]):
    """Recursively search JSON structures for reel video information."""
    if isinstance(obj, dict):
        code = obj.get("code") or obj.get("shortcode")
        video_url = None

        # Check candidate video versions (pick highest resolution progressive video)
        if "video_versions" in obj and isinstance(obj["video_versions"], list) and obj["video_versions"]:
            sorted_versions = sorted(
                obj["video_versions"],
                key=lambda x: x.get("width", 0) if isinstance(x, dict) else 0,
                reverse=True
            )
            for v in sorted_versions:
                if isinstance(v, dict) and "url" in v:
                    video_url = v["url"]
                    break

        if not video_url:
            video_url = obj.get("video_url")

        if code:
            existing = results.get(code, {})
            caption = ""
            if "caption" in obj and isinstance(obj["caption"], dict):
                caption = obj["caption"].get("text", "")
            elif "edge_media_to_caption" in obj:
                edges = obj["edge_media_to_caption"].get("edges", [])
                if edges and "node" in edges[0]:
                    caption = edges[0]["node"].get("text", "")

            date_val = obj.get("taken_at") or obj.get("taken_at_timestamp")
            date_str = None
            if date_val:
                try:
                    date_str = datetime.utcfromtimestamp(date_val).isoformat()
                except Exception:
                    pass

            duration = None
            if "video_duration" in obj and obj.get("video_duration") is not None:
                try:
                    duration = float(obj["video_duration"])
                except (ValueError, TypeError):
                    pass
            if duration is None and video_url:
                duration = extract_duration_from_url(video_url)

            views_raw = (
                obj.get("play_count")
                or obj.get("video_play_count")
                or obj.get("view_count")
                or obj.get("video_view_count")
            )
            views = parse_views_str(views_raw)

            results[code] = {
                "shortcode": code,
                "video_url": video_url or existing.get("video_url"),
                "duration": duration if duration is not None else existing.get("duration"),
                "views": views if views is not None else existing.get("views"),
                "caption": caption or existing.get("caption", ""),
                "date": date_str or existing.get("date"),
                "likes": obj.get("like_count") or (obj.get("edge_liked_by", {}).get("count") if isinstance(obj.get("edge_liked_by"), dict) else existing.get("likes", 0)),
            }

        for v in obj.values():
            extract_reels_from_json(v, results)

    elif isinstance(obj, list):
        for item in obj:
            extract_reels_from_json(item, results)


def download_single_video(url: str, output_path: Path, session: requests.Session, max_retries: int = 3) -> bool:
    """Download video with streaming, retry logic, and MP4 container verification."""
    for attempt in range(1, max_retries + 1):
        try:
            with session.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()

                first_chunk = True
                valid_mp4 = False
                total_bytes = 0

                with open(output_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            if first_chunk:
                                first_chunk = False
                                # Standard MP4 files always contain the 'ftyp' box in the first 32 bytes
                                if b"ftyp" not in chunk[:32]:
                                    print("      ⚠️ Stream is not a standalone MP4 (missing ftyp header), skipping.")
                                    break
                                valid_mp4 = True
                            f.write(chunk)
                            total_bytes += len(chunk)

                if valid_mp4 and output_path.exists() and total_bytes > 100000:
                    with open(output_path, "rb") as check_f:
                        header = check_f.read(32)
                        if b"ftyp" in header:
                            return True
                    print("      ⚠️ Downloaded file header invalid, retrying...")
                else:
                    if output_path.exists():
                        output_path.unlink(missing_ok=True)
                    print(f"      ⚠️ Incomplete video ({total_bytes} bytes), retrying...")
        except Exception as e:
            if attempt == max_retries:
                print(f"      ❌ Download error after {max_retries} attempts: {e}")
                if output_path.exists():
                    output_path.unlink(missing_ok=True)
                return False
            time.sleep(2)
    return False


def fetch_video_url_for_shortcode(page: Page, shortcode: str, captured_reels: dict) -> Optional[str]:
    """Fetch video url directly by visiting reel page with response interception and HTML JSON script parsing."""
    # Check if already captured with valid video_url
    if shortcode in captured_reels and captured_reels[shortcode].get("video_url"):
        return captured_reels[shortcode]["video_url"]

    def on_reel_response(resp):
        url = resp.url
        if any(k in url for k in ["graphql", "api/v1"]):
            try:
                txt = resp.text()
                # Only extract if response actually mentions our target shortcode
                if "video_versions" in txt and shortcode in txt:
                    data = json.loads(txt)
                    extract_reels_from_json(data, captured_reels)
            except Exception:
                pass

    page.on("response", on_reel_response)
    try:
        page.goto(f"https://www.instagram.com/reel/{shortcode}/", wait_until="domcontentloaded", timeout=20000)
        page.wait_for_timeout(2500)
    except Exception:
        pass
    finally:
        try:
            page.remove_listener("response", on_reel_response)
        except Exception:
            pass

    # Source 1: Intercepted response matched shortcode
    if shortcode in captured_reels and captured_reels[shortcode].get("video_url"):
        return captured_reels[shortcode]["video_url"]

    # Source 2: HTML JSON script tags (<script type="application/json">)
    try:
        html = page.content()
        scripts = re.findall(r'<script[^>]*type="application/json"[^>]*>(.*?)</script>', html)
        for s in scripts:
            if shortcode in s and "video_versions" in s:
                try:
                    data = json.loads(s)
                    extract_reels_from_json(data, captured_reels)
                except Exception:
                    pass
    except Exception:
        pass

    if shortcode in captured_reels and captured_reels[shortcode].get("video_url"):
        return captured_reels[shortcode]["video_url"]

    # Source 3: Target video_versions embedded in HTML
    try:
        html = page.content().replace(r"\/", "/")
        matches = re.findall(r'"video_versions"\s*:\s*(\[[^\]]+\])', html)
        for m in matches:
            try:
                versions = json.loads(m)
                best = sorted(
                    versions,
                    key=lambda x: x.get("width", 0) if isinstance(x, dict) else 0,
                    reverse=True
                )[0]
                u = best.get("url")
                if u:
                    dur = extract_duration_from_url(u)
                    if shortcode not in captured_reels:
                        captured_reels[shortcode] = {"shortcode": shortcode}
                    captured_reels[shortcode]["video_url"] = u
                    if dur is not None:
                        captured_reels[shortcode]["duration"] = dur
                    return u
            except Exception:
                pass
    except Exception:
        pass

    return None





def download_reels_browser(
    target_username: str,
    resume: bool = False,
    max_duration: Optional[float] = None,
    min_views: Optional[Union[int, str]] = None,
    headless: Optional[bool] = None,
):
    """
    Main Playwright-based download orchestrator.
    Navigates to the user's reels tab, discovers reels in strict latest-first order,
    extracts views and duration metrics, enforces filtering, and downloads progressive MP4s.
    """
    config = load_config()
    data_dir = SCRIPT_DIR / config.get("browser_data_dir", "./browser_data")
    is_headless = config.get("browser_headless", True) if headless is None else headless
    if max_duration is None:
        max_duration = config.get("max_duration_seconds")
    if min_views is None:
        min_views = parse_views_str(config.get("min_views"))
    elif isinstance(min_views, str):
        min_views = parse_views_str(min_views)

    output_dir = Path(config["output_directory"]) / target_username
    output_dir.mkdir(parents=True, exist_ok=True)
    tracker = ProgressTracker(target_username)

    if tracker.count > 0:
        print(f"🔄 Progress tracker loaded: {tracker.count} reels previously recorded for @{target_username}.")

    print(f"\n{'='*60}")
    print(f"  🎬 Playwright Browser Engine: @{target_username}")
    print(f"  📁 Output Directory: {output_dir.resolve()}")
    print(f"  🛡️ Headless: {is_headless} | Profile: {data_dir.name}")
    if min_views is not None:
        print(f"  👁️ Min Views: >= {min_views:,} (reels with fewer views will be skipped)")
    if max_duration is not None:
        print(f"  ⏱️ Max Duration: <= {max_duration:.1f}s (reels longer will be skipped)")
    print(f"{'='*60}\n")

    captured_reels: Dict[str, dict] = {}
    found_shortcodes: List[str] = []

    with sync_playwright() as p:
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ]
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(data_dir),
            headless=is_headless,
            args=args,
            viewport={"width": 1280, "height": 900},
        )

        page = context.pages[0] if context.pages else context.new_page()

        # Auto-seed cookies from saved sessions if browser_data does not have sessionid yet
        existing_cookies = context.cookies()
        if not any(c.get("name") == "sessionid" for c in existing_cookies):
            sessions_dir = SCRIPT_DIR / "sessions"
            session_files = list(sessions_dir.glob("*_session")) if sessions_dir.exists() else []
            if session_files:
                import pickle
                try:
                    with open(session_files[0], "rb") as sf:
                        saved_cookies = pickle.load(sf)
                    if isinstance(saved_cookies, dict) and "sessionid" in saved_cookies:
                        cookies_to_add = [
                            {"name": k, "value": v, "domain": ".instagram.com", "path": "/"}
                            for k, v in saved_cookies.items()
                        ]
                        context.add_cookies(cookies_to_add)
                        print(f"🔑 Auto-seeded browser cookies from {session_files[0].name}")
                except Exception as e:
                    print(f"⚠️ Could not auto-seed session: {e}")

        # Listen to GraphQL / API responses to intercept reel data
        def handle_response(response):
            url = response.url
            if any(k in url for k in ["graphql/query", "api/graphql", "/graphql", "api/v1"]):
                try:
                    txt = response.text()
                    if "video_versions" in txt or "shortcode" in txt or "code" in txt or "play_count" in txt:
                        data = json.loads(txt)
                        extract_reels_from_json(data, captured_reels)
                except Exception:
                    pass

        page.on("response", handle_response)

        reels_url = f"https://www.instagram.com/{target_username}/reels/"
        print(f"🔍 Navigating to: {reels_url}")
        try:
            page.goto(reels_url, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception as e:
            print(f"⚠️ Page load warning: {e}")

        # Check for login prompt or checkpoint
        current_url = page.url
        if "accounts/login" in current_url:
            print("⚠️ Not logged in! Instagram redirected to login page.")
            print("Please run: python downloader.py --engine browser --browser-login")
            context.close()
            return

        # Prepare requests session with browser cookies
        browser_cookies = context.cookies()
        http_session = requests.Session()
        user_agent = page.evaluate("navigator.userAgent")
        http_session.headers.update({
            "User-Agent": user_agent,
            "Referer": "https://www.instagram.com/",
            "Accept-Language": "en-US,en;q=0.9",
        })
        for c in browser_cookies:
            http_session.cookies.set(c["name"], c["value"], domain=c.get("domain", ".instagram.com"))

        # Collection Phase with Scroll Simulation (strictly preserving chronological order)
        print("📜 Scrolling page and discovering Reels (in latest-to-oldest order)...")
        scroll_min = config.get("browser_scroll_delay_ms_min", 2000) / 1000.0
        scroll_max = config.get("browser_scroll_delay_ms_max", 5000) / 1000.0
        max_downloads = config.get("max_downloads_per_session", 100)

        consecutive_no_new = 0
        scroll_count = 0
        max_scrolls = 60

        while scroll_count < max_scrolls:
            # Query DOM for reel links
            links = page.query_selector_all("a[href*='/reel/']")
            for l in links:
                href = l.get_attribute("href")
                if href:
                    m = re.search(r"/(?:reel|reels)/([A-Za-z0-9_-]+)", href)
                    if m:
                        sc = m.group(1)
                        if sc not in found_shortcodes:
                            found_shortcodes.append(sc)
                        if sc not in captured_reels:
                            captured_reels[sc] = {"shortcode": sc, "video_url": None}

                        # Extract views from DOM inner_text (e.g. "187K", "31.3K")
                        if captured_reels[sc].get("views") is None:
                            try:
                                text_val = l.inner_text().strip()
                                dom_views = parse_views_str(text_val)
                                if dom_views is not None:
                                    captured_reels[sc]["views"] = dom_views
                            except Exception:
                                pass

            ready_count = sum(1 for r in captured_reels.values() if r.get("video_url"))
            print(f"   📊 Discovered {len(found_shortcodes)} reels | {ready_count} direct video streams captured", flush=True)

            if len(found_shortcodes) >= max_downloads:
                print(f"🎯 Reached target count of {max_downloads} reels for this session.", flush=True)
                break

            prev_total = len(found_shortcodes)
            page.evaluate("window.scrollBy(0, window.innerHeight * 1.5);")
            time.sleep(random.uniform(1.8, 2.5))
            if scroll_count % 3 == 0:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1.5)

            if len(found_shortcodes) == prev_total:
                consecutive_no_new += 1
                if consecutive_no_new >= 8 and scroll_count >= 15:
                    print("🏁 Reached end of reels or no new items loading.", flush=True)
                    break
            else:
                consecutive_no_new = 0

            scroll_count += 1

        print(f"\n📊 Total reels discovered: {len(found_shortcodes)}", flush=True)

        # Download Phase: Process in strictly latest order
        downloaded = 0
        skipped = 0
        errors = 0
        batch_counter = 0

        batch_size = config.get("batch_size", 5)
        batch_pause = config.get("batch_pause_minutes", 3) * 60
        min_delay = config.get("min_delay_seconds", 30)
        max_delay = config.get("max_delay_seconds", 90)

        for idx, sc in enumerate(found_shortcodes, start=1):
            if downloaded >= max_downloads:
                print(f"\n🛑 Reached session limit ({max_downloads} reels).")
                break

            reel_url = f"https://www.instagram.com/reel/{sc}/"
            mp4_file = output_dir / f"{sc}.mp4"

            # Duplicate check: Progress JSON and local disk check
            if tracker.is_downloaded(sc, reel_url) or (mp4_file.exists() and mp4_file.stat().st_size > 100000):
                print(f"⏩ [{idx}/{len(found_shortcodes)}] Already downloaded: {sc} ({reel_url})", flush=True)
                if not tracker.is_downloaded(sc, reel_url):
                    tracker.mark_downloaded(sc, reel_url)
                skipped += 1
                continue

            reel_info = captured_reels.get(sc, {})
            video_url = reel_info.get("video_url")
            duration = reel_info.get("duration")
            views = reel_info.get("views")

            # 1. Fast Pre-filter: Check min_views if already known from DOM / GraphQL
            if min_views is not None and views is not None and views < min_views:
                print(f"⏭️  [{idx}/{len(found_shortcodes)}] Skipping reel {sc}: views ({views:,}) < min ({min_views:,})", flush=True)
                skipped += 1
                continue

            # 2. Fast Pre-filter: Check max_duration if already known
            if max_duration is not None and duration is not None and duration > max_duration:
                print(f"⏭️  [{idx}/{len(found_shortcodes)}] Skipping reel {sc}: duration ({duration:.1f}s) > max ({max_duration:.1f}s)", flush=True)
                skipped += 1
                continue

            # 3. Resolve video URL if not yet captured
            if not video_url:
                print(f"\n🔎 [{idx}/{len(found_shortcodes)}] Resolving reel page for {sc}...", flush=True)
                video_url = fetch_video_url_for_shortcode(page, sc, captured_reels)
                reel_info = captured_reels.get(sc, {})
                duration = reel_info.get("duration")
                views = reel_info.get("views")

            if not video_url:
                print(f"⚠️ Could not resolve video URL for {sc}, skipping.", flush=True)
                errors += 1
                continue

            # 4. Resolve duration if still None
            if duration is None:
                duration = get_reel_duration(sc, video_url, captured_reels, page)
                if duration is not None:
                    captured_reels[sc]["duration"] = duration

            # 5. Check min_views filter after page resolution
            if min_views is not None and views is not None and views < min_views:
                print(f"⏭️  [{idx}/{len(found_shortcodes)}] Skipping reel {sc}: views ({views:,}) < min ({min_views:,})", flush=True)
                skipped += 1
                continue

            # 6. Check max_duration filter after page resolution
            if max_duration is not None and duration is not None and duration > max_duration:
                print(f"⏭️  [{idx}/{len(found_shortcodes)}] Skipping reel {sc}: duration ({duration:.1f}s) > max ({max_duration:.1f}s)", flush=True)
                skipped += 1
                continue

            dur_str = f" ({duration:.1f}s)" if duration is not None else ""
            views_str = f" [👁️ {views:,} views]" if views is not None else ""
            print(f"📥 [{downloaded + 1}/{min(max_downloads, len(found_shortcodes))}] Downloading: {sc}.mp4{dur_str}{views_str}", flush=True)

            success = download_single_video(video_url, mp4_file, http_session)
            if success:
                downloaded += 1
                batch_counter += 1

                meta = {
                    "shortcode": sc,
                    "url": reel_url,
                    "duration_seconds": duration,
                    "views": views,
                    "caption": reel_info.get("caption", ""),
                    "date": reel_info.get("date"),
                    "likes": reel_info.get("likes", 0),
                    "downloaded_at": datetime.now().isoformat(),
                }
                tracker.mark_downloaded(sc, reel_url, meta)

                # Save metadata
                if config.get("save_metadata", True):
                    meta_file = output_dir / f"{sc}_meta.json"
                    with open(meta_file, "w", encoding="utf-8") as mf:
                        json.dump(meta, mf, indent=2, ensure_ascii=False)

                # Throttling
                if batch_counter >= batch_size:
                    batch_counter = 0
                    pause_time = batch_pause + random.uniform(-20, 40)
                    print(f"⏸️ Batch limit reached ({batch_size} reels). Pausing for {pause_time / 60:.1f} minutes...")
                    time.sleep(pause_time)
                else:
                    delay = random.uniform(min_delay, max_delay)
                    print(f"   ⏱️ Waiting {delay:.0f}s before next download...")
                    time.sleep(delay)
            else:
                errors += 1

        context.close()

    print(f"\n{'='*60}")
    print("  ✅ Download Summary (Playwright Browser)")
    print(f"  📥 Downloaded: {downloaded}")
    print(f"  ⏭️ Skipped:    {skipped}")
    print(f"  ❌ Errors:     {errors}")
    print(f"  📁 Output:     {output_dir.resolve()}")
    print(f"{'='*60}\n")


def extract_shortcode(url_or_code: str) -> str:
    """Extract Instagram reel shortcode from a URL or raw shortcode string."""
    url_or_code = url_or_code.strip()
    m = re.search(r"/(?:reel|reels|p)/([A-Za-z0-9_-]+)", url_or_code)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{5,35}", url_or_code):
        return url_or_code
    return ""


def extract_audio_ffmpeg(
    video_path: Union[str, Path],
    audio_path: Optional[Union[str, Path]] = None,
    format: str = "mp3",
) -> Optional[Path]:
    """
    Extracts an audio track from a video file using FFmpeg.
    Returns Path to the extracted audio file, or None if extraction fails.
    """
    video_path = Path(video_path)
    if not video_path.exists():
        return None
    if audio_path is None:
        audio_path = video_path.with_suffix(f".{format}")
    else:
        audio_path = Path(audio_path)

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
            print(f"⚠️ FFmpeg audio extraction warning: {proc.stderr[:200]}")
    except Exception as e:
        print(f"⚠️ Could not execute FFmpeg for audio extraction: {e}")
    return None


def download_single_reel_by_url(
    reel_url: str,
    output_dir: Optional[Path] = None,
    max_duration: Optional[float] = None,
    min_views: Optional[Union[int, str]] = None,
    headless: Optional[bool] = None,
    return_info: bool = False,
    extract_audio: bool = False,
    audio_format: str = "mp3",
) -> Union[bool, dict]:
    """
    Downloads a single Instagram reel directly by its link/URL.
    """
    shortcode = extract_shortcode(reel_url)
    if not shortcode:
        print(f"❌ Invalid Instagram reel URL or shortcode: {reel_url}")
        print("   Supported formats:")
        print("   - https://www.instagram.com/reel/C8.../")
        print("   - https://www.instagram.com/p/C8.../")
        print("   - Or just the shortcode directly (e.g. C8...)")
        if return_info:
            return {"status": "error", "error": f"Invalid Instagram reel URL: {reel_url}"}
        return False

    config = load_config()
    data_dir = SCRIPT_DIR / config.get("browser_data_dir", "./browser_data")
    is_headless = config.get("browser_headless", True) if headless is None else headless
    if max_duration is None:
        max_duration = config.get("max_duration_seconds")
    if min_views is None:
        min_views = parse_views_str(config.get("min_views"))
    elif isinstance(min_views, str):
        min_views = parse_views_str(min_views)

    if output_dir is None:
        target_dir = Path(config["output_directory"]) / "single_reels"
    else:
        target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}")
    print(f"  🎬 Single Reel Downloader (Playwright Browser)")
    print(f"  🔗 Target: {reel_url}")
    print(f"  🏷️ Shortcode: {shortcode}")
    print(f"  📁 Output Directory: {target_dir.resolve()}")
    if min_views is not None:
        print(f"  👁️ Min Views: >= {min_views:,} (fewer views will be skipped)")
    if max_duration is not None:
        print(f"  ⏱️ Max Duration: <= {max_duration:.1f}s (longer will be skipped)")
    print(f"{'='*60}\n")

    with sync_playwright() as p:
        args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
        ]
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(data_dir),
            headless=is_headless,
            args=args,
            viewport={"width": 1280, "height": 900},
        )

        # Auto-seed cookies from saved sessions if browser_data does not have sessionid yet
        existing_cookies = context.cookies()
        if not any(c.get("name") == "sessionid" for c in existing_cookies):
            sessions_dir = SCRIPT_DIR / "sessions"
            session_files = list(sessions_dir.glob("*_session")) if sessions_dir.exists() else []
            if session_files:
                import pickle
                try:
                    with open(session_files[0], "rb") as sf:
                        saved_cookies = pickle.load(sf)
                    if isinstance(saved_cookies, dict) and "sessionid" in saved_cookies:
                        cookies_to_add = [
                            {"name": k, "value": v, "domain": ".instagram.com", "path": "/"}
                            for k, v in saved_cookies.items()
                        ]
                        context.add_cookies(cookies_to_add)
                        print(f"🔑 Auto-seeded browser cookies from {session_files[0].name}")
                except Exception as e:
                    print(f"⚠️ Could not auto-seed session: {e}")

        page = context.pages[0] if context.pages else context.new_page()

        # Prepare requests HTTP session with browser cookies
        http_session = requests.Session()
        user_agent = page.evaluate("navigator.userAgent")
        http_session.headers.update({
            "User-Agent": user_agent,
            "Referer": "https://www.instagram.com/",
            "Accept-Language": "en-US,en;q=0.9",
        })
        for c in context.cookies():
            http_session.cookies.set(c["name"], c["value"], domain=c.get("domain", ".instagram.com"))

        captured_reels = {}
        print(f"🔎 Resolving video stream for {shortcode}...")
        video_url = fetch_video_url_for_shortcode(page, shortcode, captured_reels)

        if not video_url:
            print(f"❌ Could not resolve video URL for {shortcode}. The post may be private or deleted.")
            context.close()
            if return_info:
                return {"status": "error", "error": f"Could not resolve video URL for {shortcode}. The post may be private or deleted."}
            return False

        reel_info = captured_reels.get(shortcode, {})
        views = reel_info.get("views")
        if min_views is not None and views is not None and views < min_views:
            print(f"⏭️ Skipping reel {shortcode}: views ({views:,}) < min views ({min_views:,})")
            context.close()
            if return_info:
                return {"status": "skipped", "reason": f"views ({views:,}) < min views ({min_views:,})", "shortcode": shortcode}
            return False

        duration = get_reel_duration(shortcode, video_url, captured_reels, page)
        if max_duration is not None and duration is not None and duration > max_duration:
            print(f"⏭️ Skipping reel {shortcode}: duration ({duration:.1f}s) > max duration ({max_duration:.1f}s)")
            context.close()
            if return_info:
                return {"status": "skipped", "reason": f"duration ({duration:.1f}s) > max duration ({max_duration:.1f}s)", "shortcode": shortcode}
            return False

        dur_str = f" ({duration:.1f}s)" if duration is not None else ""
        views_str = f" [👁️ {views:,} views]" if views is not None else ""
        mp4_file = target_dir / f"{shortcode}.mp4"
        print(f"📥 Downloading: {mp4_file.name}{dur_str}{views_str}...")
        success = download_single_video(video_url, mp4_file, http_session)

        audio_path_obj = None
        meta_file = None

        if success:
            file_size_mb = mp4_file.stat().st_size / (1024 * 1024)
            print(f"\n✅ Successfully downloaded: {mp4_file.resolve()} ({file_size_mb:.2f} MB)")

            # Extract audio if requested
            if extract_audio:
                audio_file = target_dir / f"{shortcode}.{audio_format}"
                audio_path_obj = extract_audio_ffmpeg(mp4_file, audio_file, format=audio_format)
                if audio_path_obj and audio_path_obj.exists():
                    print(f"🎵 Saved audio reference: {audio_path_obj.resolve()}")

            # Save metadata if enabled
            if config.get("save_metadata", True):
                meta_file = target_dir / f"{shortcode}_meta.json"
                meta = {
                    "shortcode": shortcode,
                    "url": f"https://www.instagram.com/reel/{shortcode}/",
                    "duration_seconds": duration,
                    "views": views,
                    "caption": reel_info.get("caption", ""),
                    "date": reel_info.get("date"),
                    "likes": reel_info.get("likes", 0),
                    "author": reel_info.get("owner_username", ""),
                    "downloaded_at": datetime.now().isoformat(),
                }
                with open(meta_file, "w", encoding="utf-8") as mf:
                    json.dump(meta, mf, indent=2, ensure_ascii=False)
                print(f"📄 Saved metadata: {meta_file.resolve()}")
        else:
            print(f"❌ Failed to download video for {shortcode}.")

        context.close()

        if return_info:
            if success:
                return {
                    "status": "success",
                    "platform": "instagram",
                    "media_type": "reel",
                    "shortcode": shortcode,
                    "url": f"https://www.instagram.com/reel/{shortcode}/",
                    "video_path": str(mp4_file.resolve()),
                    "audio_path": str(audio_path_obj.resolve()) if audio_path_obj else None,
                    "metadata_path": str(meta_file.resolve()) if meta_file and meta_file.exists() else None,
                    "duration_seconds": duration,
                    "views": views,
                    "likes": reel_info.get("likes", 0),
                    "author": reel_info.get("owner_username", ""),
                    "caption": reel_info.get("caption", ""),
                    "date": reel_info.get("date"),
                }
            else:
                return {"status": "error", "error": f"Failed to download video stream for {shortcode}."}

        return success

