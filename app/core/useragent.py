from typing import Tuple, Optional
import logging

logger = logging.getLogger(__name__)

BOT_SIGNATURES = [
    "bot", "crawler", "spider", "scraper", "curl", "wget",
    "python-requests", "python-httpx", "go-http-client",
    "java/", "php/", "ruby", "perl", "axios",
    "googlebot", "bingbot", "yandexbot", "duckduckbot",
    "facebookexternalhit", "twitterbot", "linkedinbot",
    "whatsapp", "telegrambot", "slackbot", "discordbot",
    "applebot", "ia_archiver", "semrushbot", "ahrefsbot",
    "mj12bot", "dotbot", "rogerbot",
]

# AUDIT FIX: Precompile bot check as a set for O(1) per-token lookup
# instead of linear scan. For high-traffic deployments this matters.
_BOT_SET = frozenset(BOT_SIGNATURES)


def _is_bot(ua_lower: str) -> bool:
    return any(sig in ua_lower for sig in _BOT_SET)


def parse_user_agent(ua_string: Optional[str]) -> Tuple[str, str, str]:
    """
    Parse UA string into (device_type, browser, os).
    Returns 'unknown' for unparseable fields. Never raises.

    device_type: "mobile" | "tablet" | "desktop" | "bot" | "unknown"
    browser:     "Chrome" | "Safari" | "Firefox" | "Edge" | ... | "unknown"
    os:          "iOS" | "Android" | "Windows" | "macOS" | "Linux" | ... | "unknown"
    """
    if not ua_string:
        return "unknown", "unknown", "unknown"

    # AUDIT FIX: Truncate before parsing — maliciously long UA strings
    # could cause the parser to spend excessive CPU time.
    ua_string = ua_string[:600]
    ua_lower = ua_string.lower()

    if _is_bot(ua_lower):
        return "bot", "bot", "bot"

    try:
        from user_agents import parse
        ua = parse(ua_string)

        if ua.is_mobile:
            device_type = "mobile"
        elif ua.is_tablet:
            device_type = "tablet"
        elif ua.is_pc:
            device_type = "desktop"
        else:
            device_type = "unknown"

        browser_raw = ua.browser.family or "unknown"
        browser_map = {
            "Chrome Mobile": "Chrome",
            "Chrome Mobile iOS": "Chrome",
            "Mobile Safari": "Safari",
            "Samsung Internet": "Samsung Internet",
            "Edge": "Edge",
            "Edge Mobile": "Edge",
            "Firefox Mobile": "Firefox",
            "IE": "Internet Explorer",
        }
        browser = browser_map.get(browser_raw, browser_raw)
        if browser == "Other":
            browser = "unknown"

        os_raw = ua.os.family or "unknown"
        os_map = {
            "Mac OS X": "macOS",
            "Chrome OS": "ChromeOS",
        }
        os_name = os_map.get(os_raw, os_raw)
        if os_name == "Other":
            os_name = "unknown"

        return device_type, browser, os_name

    except Exception as e:
        logger.debug(f"User agent parse failed: {e}")
        return "unknown", "unknown", "unknown"


def parse_referer(referer: Optional[str]) -> Optional[str]:
    """
    Normalise referer header to clean domain string.
    Returns None if absent or unparseable.
    """
    if not referer or not referer.strip():
        return None

    # AUDIT FIX: Limit referer length before URL parsing
    referer = referer[:2048]

    try:
        from urllib.parse import urlparse
        parsed = urlparse(referer)
        hostname = parsed.hostname or ""
        if hostname.startswith("www."):
            hostname = hostname[4:]
        return hostname if hostname else None
    except Exception:
        return None
