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

    with smtplib.SMTP(cfg["server"], cfg["port"], timeout=5) as smtp:
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


def save_subscriber_to_cloud_db(entry):
    """Save subscriber entry to Vercel KV / Upstash Redis or Supabase / Postgres if configured."""
    email = entry.get("email")
    if not email:
        return

    # 1. Vercel KV / Upstash Redis
    kv_url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
    kv_token = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if kv_url and kv_token:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{kv_url.rstrip('/')}/sadd/subscribers/{email}",
                headers={"Authorization": f"Bearer {kv_token}"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.info("Saved subscriber %s to Vercel KV!", email)
        except Exception as e:
            logger.exception("Vercel KV save failed: %s", e)

    # 2. Supabase / Postgres via REST API
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = (
        os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("SUPABASE_PUBLISHABLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )
    if supabase_url and supabase_key:
        try:
            import urllib.request
            sb_data = json.dumps({"email": email, "subscribed_at": entry.get("subscribed_at")}).encode("utf-8")
            req = urllib.request.Request(
                f"{supabase_url.rstrip('/')}/rest/v1/subscribers",
                data=sb_data,
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=ignore-duplicates"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.info("Saved subscriber %s to Supabase!", email)
        except Exception as e:
            logger.exception("Supabase save failed: %s", e)

    # 3. Firebase Firestore via REST API
    firebase_project_id = os.environ.get("FIREBASE_PROJECT_ID")
    if firebase_project_id:
        try:
            import urllib.parse
            import urllib.request
            fs_url = f"https://firestore.googleapis.com/v1/projects/{firebase_project_id}/databases/(default)/documents/subscribers"
            fs_data = json.dumps({
                "fields": {
                    "email": {"stringValue": email},
                    "subscribed_at": {"stringValue": entry.get("subscribed_at", "")}
                }
            }).encode("utf-8")
            req = urllib.request.Request(
                fs_url,
                data=fs_data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                logger.info("Saved subscriber %s to Firebase Firestore!", email)
        except Exception as e:
            logger.exception("Firebase save failed: %s", e)


def _load_subscribers():
    """Load the subscriber list from Supabase, Firebase, Vercel KV, data/subscribers.json, or /tmp/subscribers.json."""
    seen = set()
    result = []

    # 1. Try loading from Supabase
    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = (
        os.environ.get("SUPABASE_ANON_KEY")
        or os.environ.get("SUPABASE_PUBLISHABLE_KEY")
        or os.environ.get("SUPABASE_KEY")
        or os.environ.get("SUPABASE_SECRET_KEY")
        or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    )
    if supabase_url and supabase_key:
        try:
            import urllib.request
            sb_url = f"{supabase_url.rstrip('/')}/rest/v1/subscribers?select=email"
            req = urllib.request.Request(
                sb_url,
                headers={
                    "apikey": supabase_key,
                    "Authorization": f"Bearer {supabase_key}"
                }
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data:
                    em = item.get("email") if isinstance(item, dict) else item
                    if em and em not in seen:
                        seen.add(em)
                        result.append(em)
        except Exception:
            pass

    # 1. Try loading from Firebase Firestore
    firebase_project_id = os.environ.get("FIREBASE_PROJECT_ID")
    if firebase_project_id:
        try:
            import urllib.request
            fs_url = f"https://firestore.googleapis.com/v1/projects/{firebase_project_id}/databases/(default)/documents/subscribers"
            req = urllib.request.Request(fs_url)
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                docs = data.get("documents", [])
                for doc in docs:
                    fields = doc.get("fields", {})
                    em = fields.get("email", {}).get("stringValue", "")
                    if em and em not in seen:
                        seen.add(em)
                        result.append(em)
        except Exception:
            pass

    # 2. Try loading from Vercel KV / Upstash
    kv_url = os.environ.get("KV_REST_API_URL") or os.environ.get("UPSTASH_REDIS_REST_URL")
    kv_token = os.environ.get("KV_REST_API_TOKEN") or os.environ.get("UPSTASH_REDIS_REST_TOKEN")
    if kv_url and kv_token:
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{kv_url.rstrip('/')}/smembers/subscribers",
                headers={"Authorization": f"Bearer {kv_token}"}
            )
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                members = data.get("result", [])
                for em in members:
                    if em and em not in seen:
                        seen.add(em)
                        result.append(em)
        except Exception:
            pass

    # 2. Try loading from local / serverless files
    paths = [DATA_DIR / "subscribers.json"]
    import tempfile
    paths.append(Path(tempfile.gettempdir()) / "subscribers.json")

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

def sync_subscriber_to_github(entry):
    """Automatically commit new subscriber to GitHub repo data/subscribers.json if GITHUB_TOKEN is set."""
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo = os.environ.get("GITHUB_REPO", "shayan-sethi/theatlasproject").strip()
    if not token or not repo:
        return

    url = f"https://api.github.com/repos/{repo}/contents/data/subscribers.json"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "Atlas-App"
    }

    try:
        import base64
        import urllib.error
        import urllib.request

        # 1. Fetch current subscribers.json from GitHub
        req = urllib.request.Request(url, headers=headers)
        sha = ""
        subscribers = []
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                sha = data.get("sha", "")
                content = base64.b64decode(data.get("content", "")).decode("utf-8")
                subscribers = json.loads(content)
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise

        # 2. Add entry if not already present
        emails = {s.get("email") if isinstance(s, dict) else s for s in subscribers}
        if entry.get("email") not in emails:
            subscribers.insert(0, entry)
            updated_bytes = json.dumps(subscribers, indent=2).encode("utf-8")
            b64_content = base64.b64encode(updated_bytes).decode("utf-8")

            payload = {
                "message": f"Auto-save subscriber: {entry['email']}",
                "content": b64_content,
            }
            if sha:
                payload["sha"] = sha

            put_data = json.dumps(payload).encode("utf-8")
            put_req = urllib.request.Request(url, data=put_data, headers=headers, method="PUT")
            with urllib.request.urlopen(put_req, timeout=5) as put_resp:
                logger.info("GitHub auto-saved subscriber %s cleanly!", entry['email'])
    except Exception as e:
        logger.exception("GitHub auto-save failed: %s", e)


def send_welcome_email(to_email, entry=None):
    """Send a branded welcome email to a new subscriber, alert admin, and auto-sync to GitHub."""
    try:
        html = _render_template(
            "welcome.html",
            site_url=_site_url(),
        )
        _send_email(to_email, "Welcome to The Atlas Project", html)

        # Admin alert so subscriber email is permanently saved in Gmail inbox
        cfg = _smtp_config()
        if cfg["email"] and to_email != cfg["email"]:
            admin_body = f"""<div style="font-family: sans-serif; padding: 20px;">
              <h2>New Subscriber Notification</h2>
              <p><strong>{to_email}</strong> just subscribed to The Atlas Project!</p>
            </div>"""
            _send_email(cfg["email"], f"New Subscriber: {to_email}", admin_body)

        # Auto-save to Cloud DB (Vercel KV / Upstash / Supabase) or GitHub repo
        if entry:
            save_subscriber_to_cloud_db(entry)
            sync_subscriber_to_github(entry)
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

def send_welcome_email_async(to_email, entry=None):
    """Fire-and-forget welcome email in a background thread."""
    t = threading.Thread(target=send_welcome_email, args=(to_email, entry), daemon=True)
    t.start()


def notify_subscribers_async(article):
    """Fire-and-forget subscriber notification in a background thread."""
    t = threading.Thread(target=notify_subscribers, args=(article,), daemon=True)
    t.start()
