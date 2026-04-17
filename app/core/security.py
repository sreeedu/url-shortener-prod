from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from jose import JWTError, jwt
import bcrypt
import hashlib
import secrets
import string
from app.core.config import settings

BASE62 = string.ascii_letters + string.digits


# ── Password ──────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """
    SHA-256 pre-hash prevents bcrypt's silent 72-byte truncation,
    then bcrypt provides the actual work factor and salt.
    """
    pre_hashed = hashlib.sha256(password.encode("utf-8")).digest()
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(pre_hashed, salt)
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        pre_hashed = hashlib.sha256(plain.encode("utf-8")).digest()
        return bcrypt.checkpw(pre_hashed, hashed.encode("utf-8"))
    except Exception:
        return False


def validate_password_strength(password: str) -> Tuple[bool, str]:
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if len(password) > 128:
        # AUDIT FIX: Unbounded password length allows DoS via giant bcrypt input.
        # SHA-256 pre-hash already removes the bcrypt 72-byte issue, but the
        # SHA-256 call itself can be slow on massive inputs. Cap at 128 chars —
        # no legitimate user needs a longer password.
        return False, "Password must be at most 128 characters"
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one number"
    return True, ""


_DUMMY_HASH: str = hash_password("dummy-timing-prevention-Xk9#mP2$")


def get_dummy_hash() -> str:
    return _DUMMY_HASH


# ── JWT ───────────────────────────────────────────────────────────────────────

def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),   # AUDIT FIX: issued-at for token age auditing
        "type": "access",
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": subject,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh",
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_admin_invite_token(invitee_id: str, inviter_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=7)
    payload = {
        "sub": invitee_id,
        "inviter_id": inviter_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "admin_invite",
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_verification_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=1)
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "email_verify",
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)



def decode_token(token: str, token_type: str = "access") -> Optional[str]:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[settings.ALGORITHM],
            # AUDIT FIX: explicitly require exp claim — reject tokens without expiry
            options={"require": ["exp", "sub", "type"]},
        )
        if payload.get("type") != token_type:
            return None
        subject = payload.get("sub")
        # AUDIT FIX: sub must be a non-empty string — reject malformed tokens
        if not subject or not isinstance(subject, str):
            return None
        return subject
    except JWTError:
        return None


# ── Password Reset ────────────────────────────────────────────────────────────

def generate_reset_token() -> Tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_reset_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


# ── Short Code ────────────────────────────────────────────────────────────────

def generate_short_code(length: int = None) -> str:
    length = length or settings.SHORT_CODE_LENGTH
    return "".join(secrets.choice(BASE62) for _ in range(length))
