import os
import json
import re
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

COMICS = [
    {"name": "Garfield", "slug": "garfield", "url": "https://www.gocomics.com/garfield"},
    {"name": "Peanuts", "slug": "peanuts", "url": "https://www.gocomics.com/peanuts"},
]

OUT_DIR = "docs"
IMG_DIR = os.path.join(OUT_DIR, "images")
FEED_PATH = os.path.join(OUT_DIR, "comics.xml")
STATE_PATH = "state.json"

# Change this to your Pages base once Pages is enabled.
# While Pages is off, leave it blank and Reeder will still show items,
# but images will work best once Pages is on.
PAGES_BASE = "https://mclars27.github.io/my-comics-rss"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def fetch_image_url(page_url: str) -> str:
    r = requests.get(page_url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.text
    soup = BeautifulSoup(html, "html.parser")

    # Meta tags first
    for meta in [
        ("property", "og:image"),
        ("property", "og:image:secure_url"),
        ("name", "twitter:image"),
        ("name", "twitter:image:src"),
    ]:
        tag = soup.find("meta", attrs={meta[0]: meta[1]})
        if tag and tag.get("content"):
            return tag["content"].strip()

    # Raw HTML fallback for common hosts
    patterns = [
        r"https://featureassets\.gocomics\.com/assets/[^\s\"']+",
        r"https://gocomicscmsassets\.gocomics\.com/[^\s\"']+",
        r"https://assets\.amuniversal\.com/[^\s\"']+",
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m:
            return m.group(0).strip()

    raise RuntimeError("Could not find comic image URL")

def download_image(img_url: str, filename_base: str) -> str:
    os.makedirs(IMG_DIR, exist_ok=True)

    # Use a stable hash so we don't re-download the same image
    h = hashlib.sha1(img_url.encode("utf-8")).hexdigest()[:12]

    # Guess extension
    path = urlparse(img_url).path.lower()
    ext = ".jpg"
    for candidate in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
        if candidate in path:
            ext = candidate
            break

    local_name = f"{filename_base}-{h}{ext}"
    local_path = os.path.join(IMG_DIR, local_name)

    if not os.path.exists(local_path):
        ir = requests.get(img_url, headers=HEADERS, timeout=30)
        ir.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(ir.content)

    # Return the URL that RSS readers can load
    if PAGES_BASE:
        return f"{PAGES_BASE}/images/{local_name}"
    else:
        # fallback to relative path (works once hosted)
        return f"images/{local_name}"

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
        img_url = fetch_image_url(c["url"])
        key = f"{c['slug']}:{today}"

        # If unchanged today, skip
        if state["seen"].get(key) == img_url:
            continue

        # Download and host the image ourselves
        hosted_img = download_image(img_url, f"{c['slug']}-{today}")

        state["seen"][key] = img_url

        new_items.append({
            "id": key,
            "title": f"{c['name']} — {today}",
            "link": c["url"],
            "date": now.isoformat(),
            "html": f'<p><a href="{c["url"]}">{c["name"]}</a></p><p><img src="{hosted_img}" /></p>',
        })

    state["history"] = (new_items + state["history"])[:90]
    build_feed(state["history"])
    save_state(state)

if __name__ == "__main__":
    main()
