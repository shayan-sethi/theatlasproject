import json
import re
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, abort, redirect, render_template, request, send_from_directory, url_for


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
ARTICLES_PATH = DATA_DIR / "articles.json"

CONTINENTS = {
    "africa": {
        "name": "Africa",
        "dek": "Power, climate, culture, and markets across a continent of fast-moving stories.",
        "accent": "#ec9a74",
        "theme": "theme-africa",
    },
    "asia": {
        "name": "Asia",
        "dek": "Supply chains, elections, cities, technology, and security from the world's largest region.",
        "accent": "#96a4f4",
        "theme": "theme-asia",
    },
    "europe": {
        "name": "Europe",
        "dek": "Policy, energy, migration, defense, and climate from the European desk.",
        "accent": "#7edce2",
        "theme": "theme-europe",
    },
    "north-america": {
        "name": "North America",
        "dek": "Politics, trade, climate, cities, and culture across the United States, Canada, and Mexico.",
        "accent": "#8bd2a4",
        "theme": "theme-north-america",
    },
    "south-america": {
        "name": "South America",
        "dek": "Resources, elections, forests, cities, and regional power across South America.",
        "accent": "#e6c46a",
        "theme": "theme-south-america",
    },
    "oceania": {
        "name": "Oceania",
        "dek": "Pacific politics, climate adaptation, security, and island futures.",
        "accent": "#c69ee8",
        "theme": "theme-oceania",
    },
    "antarctica": {
        "name": "Antarctica",
        "dek": "Science, climate signals, logistics, and geopolitics from the southern ice.",
        "accent": "#d6e8ee",
        "theme": "theme-antarctica",
    },
}

PAGES = {
    "articles": {
        "title": "Articles",
        "dek": "Field notes, briefings, and long-form analysis from the Atlas desk.",
    },
    "infographics": {
        "title": "Infographics",
        "dek": "Visual explainers for the numbers, places, and systems shaping the world.",
    },
    "about": {
        "title": "About Atlas",
        "dek": "A small editorial project for curious readers who like their world news mapped.",
    },
}

app = Flask(__name__)


def slugify(text):
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug or "article"


def load_articles():
    if not ARTICLES_PATH.exists():
        return []
    return json.loads(ARTICLES_PATH.read_text(encoding="utf-8"))


def save_articles(articles):
    DATA_DIR.mkdir(exist_ok=True)
    ARTICLES_PATH.write_text(json.dumps(articles, indent=2), encoding="utf-8")


def articles_for_continent(continent_slug):
    return [
        article for article in load_articles()
        if article.get("continent") == continent_slug
    ]


@app.route("/")
def index():
    return render_template("index.html", articles=load_articles()[:3])


@app.route("/data/countries-by-continents.csv")
def continent_csv():
    return send_from_directory(BASE_DIR, "Countries by continents.csv")


@app.route("/subscribe", methods=["POST"])
def subscribe():
    email = request.form.get("email", "").strip()
    if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
        return redirect(request.referrer or url_for("index"))

    subs_path = DATA_DIR / "subscribers.json"
    subscribers = []
    if subs_path.exists():
        try:
            subscribers = json.loads(subs_path.read_text(encoding="utf-8"))
        except Exception:
            subscribers = []

    emails = {s.get("email") if isinstance(s, dict) else s for s in subscribers}
    if email not in emails:
        entry = {"email": email, "subscribed_at": datetime.now(timezone.utc).isoformat()}
        subscribers.insert(0, entry)
        DATA_DIR.mkdir(exist_ok=True)
        subs_path.write_text(json.dumps(subscribers, indent=2), encoding="utf-8")

    return redirect(request.referrer or url_for("index"))


@app.route("/article/<article_slug>")
def article_detail(article_slug):
    article = next(
        (item for item in load_articles() if item.get("slug") == article_slug),
        None,
    )
    if not article:
        abort(404)
    continent = CONTINENTS.get(article["continent"])
    return render_template("article.html", article=article, continent=continent)


@app.route("/<continent_slug>")
def continent(continent_slug):
    page = PAGES.get(continent_slug)
    if page:
        return render_template("page.html", page=page, articles=load_articles())

    continent_data = CONTINENTS.get(continent_slug)
    if not continent_data:
        abort(404)
    return render_template(
        "continent.html",
        continent=continent_data,
        continent_slug=continent_slug,
        articles=articles_for_continent(continent_slug),
    )


if __name__ == "__main__":
    app.run(debug=True)
