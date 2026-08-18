"""
Atlas Email Service
───────────────────
Handles sending welcome emails to new subscribers and
briefing emails to all subscribers when a new article drops.

Reads SMTP config from environment variables:
  ATLAS_SMTP_SERVER   (default: smtp.gmail.com)
  ATLAS_SMTP_PORT     (default: 587)
  ATLAS_SMTP_EMAIL    (required)
  ATLAS_SMTP_PASSWORD (required)
  ATLAS_SITE_URL      (default: http://localhost:8000)
"""

import json
import logging
import os
import smtplib
import threading
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates" / "emails"


def _load_env_file():
    """Load variables from .env into os.environ if .env exists."""
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        try:
            for line in env_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))
        except Exception:
            pass

_load_env_file()


def _smtp_config():
    """Return a dict of SMTP settings from environment variables."""
    _load_env_file()
    server = os.environ.get("ATLAS_SMTP_SERVER", "smtp.gmail.com")
    port = int(os.environ.get("ATLAS_SMTP_PORT", "587"))
    email = os.environ.get("ATLAS_SMTP_EMAIL", "")
    password = os.environ.get("ATLAS_SMTP_PASSWORD", "")
    return {"server": server, "port": port, "email": email, "password": password}


def _site_url():
    """Return the configured site URL (no trailing slash)."""
    return os.environ.get("ATLAS_SITE_URL", "http://localhost:8000").rstrip("/")


def _send_email(to_email, subject, html_body):
    """Send a single HTML email via SMTP. Raises on failure."""
    cfg = _smtp_config()
    if not cfg["email"] or not cfg["password"]:
        logger.warning("SMTP credentials not configured — skipping email to %s", to_email)
        return

    msg = MIMEMultipart("alternative")
    msg["From"] = f"The Atlas Project <{cfg['email']}>"
    msg["To"] = to_email
    msg["Subject"] = subject

    # Plain-text fallback
    plain = f"{subject}\n\nVisit The Atlas Project: {_site_url()}"
    msg.attach(MIMEText(plain, "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(cfg["server"], cfg["port"]) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.ehlo()
        smtp.login(cfg["email"], cfg["password"])
        smtp.sendmail(cfg["email"], to_email, msg.as_string())

    logger.info("Email sent to %s: %s", to_email, subject)


def _render_template(template_name, **kwargs):
    """Simple template renderer — replaces {{ key }} placeholders."""
    path = TEMPLATES_DIR / template_name
    html = path.read_text(encoding="utf-8")
    for key, value in kwargs.items():
        html = html.replace("{{ " + key + " }}", str(value))
    return html


def _load_subscribers():
    """Load the subscriber list from data/subscribers.json or /tmp/subscribers.json."""
    subscribers = []
    paths = [DATA_DIR / "subscribers.json"]
    import tempfile
    paths.append(Path(tempfile.gettempdir()) / "subscribers.json")

    seen = set()
    result = []
    for subs_path in paths:
        if subs_path.exists():
            try:
                data = json.loads(subs_path.read_text(encoding="utf-8"))
                for s in data:
                    em = s.get("email") if isinstance(s, dict) else s
                    if em and em not in seen:
                        seen.add(em)
                        result.append(em)
            except Exception:
                pass
    return result


# ── Public API ───────────────────────────────────────────────

def send_welcome_email(to_email):
    """Send a branded welcome email to a new subscriber."""
    try:
        html = _render_template(
            "welcome.html",
            site_url=_site_url(),
        )
        _send_email(to_email, "Welcome to The Atlas Project", html)
    except Exception:
        logger.exception("Failed to send welcome email to %s", to_email)


def notify_subscribers(article):
    """
    Send a briefing email about a new article to every subscriber.

    `article` should be a dict with keys:
      slug, title, summary, continent_name, continent
    """
    subscribers = _load_subscribers()
    if not subscribers:
        logger.info("No subscribers to notify.")
        return

    site = _site_url()
    article_url = f"{site}/article/{article['slug']}"

    html = _render_template(
        "new_article.html",
        site_url=site,
        article_url=article_url,
        article_title=article.get("title", ""),
        article_summary=article.get("summary", ""),
        continent_name=article.get("continent_name", "Atlas"),
    )

    subject = f"New on Atlas: {article.get('title', 'A new article')}"

    sent = 0
    failed = 0
    for email in subscribers:
        try:
            _send_email(email, subject, html)
            sent += 1
        except Exception:
            logger.exception("Failed to notify %s", email)
            failed += 1

    logger.info("Notification complete: %d sent, %d failed", sent, failed)
    return {"sent": sent, "failed": failed}


# ── Background helpers ───────────────────────────────────────

def send_welcome_email_async(to_email):
    """Fire-and-forget welcome email in a background thread."""
    t = threading.Thread(target=send_welcome_email, args=(to_email,), daemon=True)
    t.start()


def notify_subscribers_async(article):
    """Fire-and-forget subscriber notification in a background thread."""
    t = threading.Thread(target=notify_subscribers, args=(article,), daemon=True)
    t.start()
