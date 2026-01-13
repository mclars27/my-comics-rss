import os
import json
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
    "User-Agent": "Mozilla/5.0 (compatible; ComicsRSS/1.0)"
}

def fetch_image(page_url):
    r = requests.get(page_url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    # Most stable selector on GoComics
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"]

    raise RuntimeError("Could not find comic image")

def load_state():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH, "r") as f:
            return json.load(f)
    return {"seen": {}, "history": []}

def save_state(state):
    with open(STATE_PATH, "w") as f:
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
        fe.pubDate(e["date"])
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
            "date": now,
            "html": f'<img src="{img_url}" />'
        })

    state["history"] = (new_items + state["history"])[:90]
    build_feed(state["history"])
    save_state(state)

if __name__ == "__main__":
    main()
