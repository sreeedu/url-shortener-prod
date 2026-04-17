import smtplib
import ssl
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

logger = logging.getLogger(__name__)


def _build_reset_email(to_email: str, reset_link: str) -> MIMEMultipart:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Reset your password"
    msg["From"] = f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>"
    msg["To"] = to_email
    # AUDIT FIX: Message-ID and Date headers prevent some spam filters from
    # flagging the email as suspicious and aid in email deliverability.
    import uuid
    from email.utils import formatdate
    msg["Message-ID"] = f"<{uuid.uuid4()}@{settings.BASE_URL.split('://')[-1].split('/')[0]}>"
    msg["Date"] = formatdate(localtime=True)

    text = f"""\
Hi,

You requested a password reset. Click the link below to set a new password.
This link expires in {settings.RESET_TOKEN_EXPIRE_MINUTES} minutes.

{reset_link}

If you did not request this, ignore this email. Your password will not change.
"""
    html = f"""\
<html><body style="font-family:sans-serif;max-width:480px;margin:auto;padding:24px;">
<h2 style="color:#1F2937;">Password Reset</h2>
<p>You requested a password reset.<br>
<strong>This link expires in {settings.RESET_TOKEN_EXPIRE_MINUTES} minutes.</strong></p>
<p>
  <a href="{reset_link}"
     style="background:#4F46E5;color:white;padding:12px 24px;
            border-radius:6px;text-decoration:none;display:inline-block;
            font-weight:600;">
    Reset Password
  </a>
</p>
<p style="color:#6B7280;font-size:13px;margin-top:24px;">
  If you did not request this, you can safely ignore this email.<br>
  Your password will not change unless you click the link above.
</p>
</body></html>
"""
    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))
    return msg


def send_password_reset_email(to_email: str, raw_token: str) -> bool:
    """
    Send reset email. Returns True on success, False on failure.
    Never raises — email failure must not crash the request.

    This is a plain synchronous function — smtplib is blocking I/O.
    It is called via FastAPI BackgroundTasks which runs it in a threadpool,
    so blocking here is safe. Declaring it async would be misleading and
    dangerous: any accidental await inside a sync SMTP call would block
    the entire event loop.
    """
    reset_link = f"{settings.FRONTEND_URL}/reset-password?token={raw_token}"

    if settings.APP_ENV == "development":
        logger.info(f"[DEV] Password reset link for {to_email}: {reset_link}")
        return True

    # AUDIT FIX: Validate SMTP config is present before attempting to send.
    # Without this, missing SMTP config produces a confusing auth error.
    if not settings.SMTP_USER or not settings.SMTP_PASSWORD or not settings.EMAILS_FROM_EMAIL:
        logger.error(
            "SMTP not configured — set SMTP_USER, SMTP_PASSWORD, EMAILS_FROM_EMAIL in .env"
        )
        return False

    try:
        msg = _build_reset_email(to_email, reset_link)
        # AUDIT FIX: Use explicit SSL context to enforce certificate verification.
        # smtplib defaults are sufficient for most cases but an explicit context
        # makes the security intent clear and prevents accidental downgrades.
        context = ssl.create_default_context()
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.EMAILS_FROM_EMAIL, to_email, msg.as_string())
        logger.info(f"Reset email sent to {to_email}")
        return True
    except smtplib.SMTPAuthenticationError:
        logger.error(f"SMTP auth failed — check SMTP_USER and SMTP_PASSWORD in .env")
        return False
    except smtplib.SMTPRecipientsRefused:
        logger.warning(f"Recipient refused by SMTP server: {to_email}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error sending to {to_email}: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending reset email to {to_email}: {e}")
        return False
