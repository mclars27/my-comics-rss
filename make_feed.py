import os
import json
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

# Comics to include
COMICS = [
    {"name": "Garfield", "slug": "garfield", "url": "https://www.gocomics.com/garfield"},
    {"name": "Peanuts", "slug": "peanuts", "url": "https://www.gocomics.com/peanuts"},
]

OUT_DIR = "docs"
FEED_PATH = os.path.join(OUT_DIR, "comics.xml")
STATE_PATH = "state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch_image(page_url: str) -> str:
    r = requests.get(page_url, headers=HEADERS, timeout=30)
    r.raise_for_status()

    html = r.text
    soup = BeautifulSoup(html, "html.parser")

    # 1) Social meta tags
    for meta in [
        ("property", "og:image"),
        ("property", "og:image:secure_url"),
        ("name", "twitter:image"),
        ("name", "twitter:image:src"),
    ]:
        tag = soup.find("meta", attrs={meta[0]: meta[1]})
        if tag and tag.get("content"):
            return tag["content"].strip()

    # 2) Fallback: search for common GoComics asset hosts in the raw HTML
    patterns = [
        r"https://featureassets\.gocomics\.com/assets/[^\s\"']+",
        r"https://gocomicscmsassets\.gocomics\.com/[^\s\"']+",
        r"https://assets\.amuniversal\.com/[^\s\"']+",
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(0).strip()

    # 3) Last fallback: any image URL that looks relevant
    for img in soup.find_all("img"):
        src = (img.get("src") or "").strip()
        if "gocomics" in src or "amuniversal" in src:
            return src

    raise RuntimeError("Could not find comic image")

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"seen": {}, "history": []}

def save_state(state):
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)

def build_feed(entries):
    fg = FeedGenerator()
    fg.title("My Daily Comics")
    fg.link(href="https://www.gocomics.com")
    fg.description("Private RSS feed for Garfield and Peanuts")
    fg.language("en")

    for e in entries:
        fe = fg.add_entry()
        fe.id(e["id"])
        fe.title(e["title"])
        fe.link(href=e["link"])
        fe.pubDate(datetime.fromisoformat(e["date"]))
        fe.description(e["html"])

    os.makedirs(OUT_DIR, exist_ok=True)
    fg.rss_file(FEED_PATH, pretty=True)

def main():
    state = load_state()
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    new_items = []

    for c in COMICS:
        img_url = fetch_image(c["url"])
        key = f"{c['slug']}:{today}"

        if state["seen"].get(key) == img_url:
            continue

        state["seen"][key] = img_url

        new_items.append({
            "id": key,
            "title": f"{c['name']} — {today}",
            "link": c["url"],
            "date": now.isoformat(),
            "html": f'<p><a href="{c["url"]}">{c["name"]}</a></p><p><img src="{img_url}" /></p>',
        })

    state["history"] = (new_items + state["history"])[:90]
    build_feed(state["history"])
    save_state(state)

if __name__ == "__main__":
    main()
