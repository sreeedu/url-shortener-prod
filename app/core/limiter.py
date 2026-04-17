from slowapi import Limiter
from slowapi.util import get_remote_address

# FIX: Rate limiting was configured in settings but never enforced anywhere.
# SlowAPI integrates directly with FastAPI and uses the client IP as the key.
# Each endpoint gets its own limit — stricter on auth, looser on redirects.
#
# Limits come from settings so they can be tuned per environment:
#   RATE_LIMIT_AUTH=10/minute      → login, signup, forgot-password
#   RATE_LIMIT_CREATE_URL=30/minute → POST /api/urls
#   RATE_LIMIT_REDIRECT=120/minute  → GET /{short_code}
#
# When a limit is exceeded, SlowAPI returns 429 Too Many Requests automatically.

limiter = Limiter(key_func=get_remote_address)
