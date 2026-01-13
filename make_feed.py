import os
import json
import re
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

# Comics to include
COMICS = [
    {"name": "Garfield", "slug": "garfield", "url": "https://www.gocomics.com/garfield"},
    {"name": "Peanuts", "slug": "peanuts", "url": "https://www.gocomics.com/peanuts"},
]

OUT_DIR = "docs"
IMG_DIR = os.path.join(OUT_DIR, "images")
FEED_PATH = os.path.join(OUT_DIR, "comics.xml")
STATE_PATH = "state.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def pages_base_url() -> str:
    """
    IMPORTANT:
    GitHub Pages is serving from the /docs folder as the site root.
    Therefore:
      - docs/comics.xml is published at: https://<owner>.github.io/<repo>/comics.xml
      - docs/images/* is published at: https://<owner>.github.io/<repo>/images/*
    So we must NOT include '/docs' in public URLs.
    """
    repo = os.getenv("GITHUB_REPOSITORY", "mclars27/my-comics-rss")
    owner, name = repo.split("/", 1)
    return f"https://{owner}.github.io/{name}"

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
    fg.link(href=pages_base_url())
    fg.description("Private RSS feed for Garfield and Peanuts")
    fg.language("en")

    for e in entries:
        fe = fg.add_entry()
        fe.id(e["id"])
        fe.title(e["title"])
        fe.link(href=e["link"])
        fe.pubDate(datetime.fromisoformat(e["date"]))
        fe.description(e["html"])

        # If you want Reeder to be extra-likely to show the image, enable this:
        # fe.enclosure(e["img"], str(e.get("length", 0)), e.get("mime", "image/jpeg"))

    os.makedirs(OUT_DIR, exist_ok=True)
    fg.rss_file(FEED_PATH, pretty=True)

def _is_social_card(url: str) -> bool:
    return ("GC_Social_FB_" in url) or ("GC_Social_" in url)

def _candidate_score(url: str) -> int:
    # Higher score = more likely to be the real strip panel
    s = 0
    if "assets.amuniversal.com/" in url:
        s += 100
    if "featureassets.gocomics.com/assets/" in url:
        s += 80
    if "gocomicscmsassets.gocomics.com/" in url:
        s += 40
    if "width=2800" in url:
        s += 10
    if _is_social_card(url):
        s -= 999
    return s

def _walk_for_urls(obj, found):
    if isinstance(obj, dict):
        for v in obj.values():
            _walk_for_urls(v, found)
    elif isinstance(obj, list):
        for v in obj:
            _walk_for_urls(v, found)
    elif isinstance(obj, str):
        if obj.startswith("http://") or obj.startswith("https://"):
            found.append(obj)

def fetch_real_strip_image_url(page_url: str) -> str:
    r = requests.get(page_url, headers=HEADERS, timeout=30)
    r.raise_for_status()
    html = r.text

    soup = BeautifulSoup(html, "html.parser")

    # Next.js payload
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data and next_data.string:
        try:
            data = json.loads(next_data.string)
            urls = []
            _walk_for_urls(data, urls)

            urls = [u for u in urls if (
                "assets.amuniversal.com/" in u
                or "featureassets.gocomics.com/assets/" in u
                or "gocomicscmsassets.gocomics.com/" in u
            ) and not _is_social_card(u)]

            if urls:
                urls.sort(key=_candidate_score, reverse=True)
                return urls[0]
        except Exception:
            pass

    # Fallback: scan raw HTML
    patterns = [
        r"https://assets\.amuniversal\.com/[A-Za-z0-9]+",
        r"https://featureassets\.gocomics\.com/assets/[^\s\"']+",
        r"https://gocomicscmsassets\.gocomics\.com/[^\s\"']+",
    ]
    for pat in patterns:
        m = re.search(pat, html)
        if m and not _is_social_card(m.group(0)):
            return m.group(0)

    raise RuntimeError("Could not find real strip image URL (site markup may have changed)")

def _guess_ext(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
        if ext in path:
            return ".jpg" if ext == ".jpeg" else ext
    return ".jpg"

def download_and_host_image(img_url: str, slug: str, day: str) -> str:
    os.makedirs(IMG_DIR, exist_ok=True)

    h = hashlib.sha1(img_url.encode("utf-8")).hexdigest()[:12]
    ext = _guess_ext(img_url)
    filename = f"{slug}-{day}-{h}{ext}"
    local_path = os.path.join(IMG_DIR, filename)

    if not os.path.exists(local_path):
        ir = requests.get(img_url, headers=HEADERS, timeout=30)
        ir.raise_for_status()
        with open(local_path, "wb") as f:
            f.write(ir.content)

    # NOTE: no /docs here
    return f"{pages_base_url()}/images/{filename}"

def main():
    state = load_state()
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    new_items = []

    for c in COMICS:
        real_img_url = fetch_real_strip_image_url(c["url"])
        key = f"{c['slug']}:{today}"

        if state["seen"].get(key) == real_img_url:
            continue

        hosted_img_url = download_and_host_image(real_img_url, c["slug"], today)
        state["seen"][key] = real_img_url

        new_items.append({
            "id": key,
            "title": f"{c['name']} - {today}",
            "link": c["url"],
            "date": now.isoformat(),
            "img": hosted_img_url,
            "html": (
                f'<p><a href="{c["url"]}">{c["name"]}</a></p>'
                f'<p><img src="{hosted_img_url}" /></p>'
            ),
        })

    state["history"] = (new_items + state["history"])[:90]
    build_feed(state["history"])
    save_state(state)

if __name__ == "__main__":
    main()
