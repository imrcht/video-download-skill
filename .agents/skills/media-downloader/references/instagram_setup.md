# Instagram Account Connection & Anti-Ban Guide

Instagram has strict anti-bot mechanisms. This guide explains how to authenticate safely and ensure long-term, ban-safe scraping.

---

## 🔑 Authentication Methods

### Method 1: Interactive Browser Login (Recommended)
This is the safest and most resilient method:
```bash
python cli.py login --browser
```
1. A real Chromium browser window will open to `https://www.instagram.com/`.
2. Log into your account manually (handles 2FA, Captchas, and verification SMS).
3. Once logged in and viewing your feed, return to the terminal and press `[Enter]`.
4. Your authenticated browser state, cookies, and localStorage are saved to `./browser_data/`.
5. Future downloads will use this session automatically in headless mode without triggering bot detection!

---

### Method 2: Browser Cookie Import (Headless / VPS)
For environments without a graphical user interface (e.g. cloud servers, Docker):
1. In your personal desktop browser, open `https://www.instagram.com/` and log in.
2. Open DevTools (`F12` or `Ctrl+Shift+I` / `Cmd+Option+I`).
3. Go to **Application** -> **Cookies** -> `https://www.instagram.com`.
4. Copy the values of:
   - `sessionid`
   - `csrftoken`
   - *(Optional)* `ds_user_id`
5. Run:
   ```bash
   python cli.py login --cookies "<sessionid>" "<csrftoken>" --username "<your_username>"
   ```

---

## 🛡️ Best Practices for Account Safety

1. **Use a Secondary / Throwaway Account**: Never use an irreplaceable personal account or brand account with high follower count for scraping. Always create a dedicated research account.
2. **Organic Throttling**: The built-in rate controller automatically introduces randomized jitter (2–6 seconds) between requests and backs off if a 429 status code is received.
3. **Session Re-use**: The engine re-uses cookies and browser profile rather than sending fresh login requests, drastically reducing suspicious activity flags.
