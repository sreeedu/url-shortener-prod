"""
Reserved short-code blocklist — single source of truth.

Used in two places:
  1. schemas/link.py  → validate_custom_code()  (user-facing 422)
  2. crud/link.py     → generate_unique_short_code()  (silent skip)

is_reserved(code) is the only public function both callers need.
"""
import re
from better_profanity import profanity as _profanity
_profanity.load_censor_words()
# ── Exact blocklist ───────────────────────────────────────────────────────────

# Your own API routes — redirect router sits at /{short_code} and is registered
# last, but these must never be stored as short codes to prevent confusion.
_API_ROUTES = {
    "api", "auth", "projects", "links", "platform",
    "health", "docs", "redoc", "openapi",
    # auth sub-routes
    "login", "signup", "logout", "refresh", "me",
    "forgot-password", "reset-password",
    "verify", "verify-email", "confirm",
}

# Static asset / web convention paths browsers and crawlers treat specially
_WEB_CONVENTIONS = {
    "static", "assets", "public", "uploads", "media", "images", "files",
    "favicon.ico", "robots.txt", "sitemap.xml", "sitemap",
    ".well-known", "manifest.json", "sw.js",
    "feed", "rss", "atom",
    "404", "500", "error", "not-found",
}

# Infrastructure / admin names — SSRF social engineering + brand confusion
_INFRASTRUCTURE = {
    "admin", "administrator", "root", "superuser", "system",
    "dashboard", "panel", "console", "portal", "backstage",
    "internal", "intranet", "private", "corporate", "network",
    "localhost", "127-0-0-1", "0-0-0-0",
    "metrics", "status", "ping", "monitor", "monitoring",
    "staging", "production", "dev", "development", "test", "demo",
}

# Phishing bait — codes that impersonate trusted brands or actions
_PHISHING = {
    # Actions that imply official communication
    "verify", "verification", "confirm", "confirmation",
    "secure", "security", "safe", "safety", "protect", "protection",
    "update", "upgrade", "activate", "activation",
    "suspend", "suspended", "restore", "recover", "recovery",
    "alert", "warning", "urgent", "important", "notice",
    # Account / financial
    "account", "accounts", "billing", "payment", "payments",
    "invoice", "receipt", "refund", "subscription",
    "wallet", "crypto", "bitcoin", "nft",
    "bank", "banking", "transfer", "wire",
    # Brand impersonation — big targets for phishing
    "google", "gmail", "youtube", "apple", "icloud",
    "microsoft", "outlook", "office", "azure",
    "amazon", "aws", "paypal", "stripe",
    "facebook", "instagram", "whatsapp", "twitter", "tiktok",
    "netflix", "spotify", "linkedin",
    # Support impersonation
    "support", "helpdesk", "help", "contact", "service",
    "feedback", "report",
}

# Abuse / reputation risk
_ABUSE = {
    "spam", "hack", "crack", "exploit", "malware", "virus",
    "trojan", "phish", "phishing", "scam", "fraud",
    "porn", "xxx", "nsfw", "adult", "sex", "nude", "nudes",
    "click", "clickhere", "go", "goto", "redirect",
}

# Namespace pollution — not harmful but reserved for your own future use
_NAMESPACE = {
    "about", "home", "index", "page", "pages",
    "blog", "news", "press", "careers", "jobs",
    "pricing", "plans", "features", "product",
    "legal", "terms", "privacy", "cookies", "license",
    "null", "undefined", "none", "true", "false",
    "new", "create", "edit", "delete", "update", "list",
    "url", "link", "short", "shorten", "shortened",
}

# Combined exact set — lowercase, checked case-insensitively
RESERVED_CODES: frozenset[str] = frozenset(
    _API_ROUTES
    | _WEB_CONVENTIONS
    | _INFRASTRUCTURE
    | _PHISHING
    | _ABUSE
    | _NAMESPACE
)


# ── Pattern blocklist ─────────────────────────────────────────────────────────
# These catch entire classes of bad codes regardless of exact spelling.

_RESERVED_PATTERNS: list[re.Pattern] = [
    # Pure numbers — look like IDs, status codes, or ports
    re.compile(r"^[0-9]+$"),

    # HTTP status code shape: 2xx, 3xx, 4xx, 5xx
    re.compile(r"^[2345][0-9]{2}$"),

    # Looks like an IP address (with hyphens instead of dots)
    re.compile(r"^[0-9]{1,3}(-[0-9]{1,3}){3}$"),

    # All same character repeated — aaaa, ----, 1111
    re.compile(r"^(.)\1+$"),

    # Starts or ends with a hyphen (also caught in schema but belt-and-suspenders)
    re.compile(r"^-|-$"),

    # Only hyphens
    re.compile(r"^-+$"),
]


# ── Public API ────────────────────────────────────────────────────────────────

def is_reserved(code: str) -> bool:
    """
    Return True if the code must not be used as a short code.

    Checks (in order, short-circuits on first match):
      1. Exact match against the combined blocklist (case-insensitive)
      2. Pattern match against reserved patterns

    Called from:
      - schemas/link.py validate_custom_code() — user-facing, returns 422
      - crud/link.py generate_unique_short_code() — silent skip on match
    """
    lowered = code.lower()

    if lowered in RESERVED_CODES:
        return True

    for pattern in _RESERVED_PATTERNS:
        if pattern.search(lowered):
            return True
        
    # profanity check — strip hyphens first so f-u-c-k is caught
    sanitized = lowered.replace("-", "")
    if _profanity.contains_profanity(sanitized):
        return True

    return False