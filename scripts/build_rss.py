import os
import re
import json
import time
import html
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from email.utils import format_datetime

INPUT = "feeds.txt"
PROGRESS = "progress.json"
OUTDIR = "output"

CHUNK = 250          # how many per run
DELAY = 1.5          # seconds between requests
RETRIES = 3

UA = "rss-archiver/1.0"


# ----------------------------
# helpers
# ----------------------------

def parse_input():
    groups = {}
    current = None
    with open(INPUT, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("[") and line.endswith("]"):
                current = line[1:-1]
                groups[current] = []
            else:
                groups[current].append(line)
    return groups


def load_progress():
    if os.path.exists(PROGRESS):
        with open(PROGRESS, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_progress(p):
    with open(PROGRESS, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2)


def fetch(url):
    for i in range(RETRIES):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
            r.raise_for_status()
            return r.text
        except Exception:
            if i + 1 == RETRIES:
                raise
            time.sleep(5)


def extract(html_text, url):
    soup = BeautifulSoup(html_text, "html.parser")

    title = soup.title.string.strip() if soup.title else url

    og = soup.find("meta", property="og:image")
    thumb = og["content"] if og else None

    if not thumb:
        img = soup.find("img")
        if img and img.get("src"):
            thumb = img["src"]

    pub = datetime.utcnow()
    return title, thumb, pub


def read_existing_urls(path):
    if not os.path.exists(path):
        return set()
    with open(path, encoding="utf-8") as f:
        return set(re.findall(r"<guid>(.*?)</guid>", f.read()))


# ----------------------------
# build
# ----------------------------

def build_feed(name, urls, start, progress):
    os.makedirs(OUTDIR, exist_ok=True)
    path = f"{OUTDIR}/{name}.xml"

    existing = read_existing_urls(path)

    subset = urls[start:start + CHUNK]
    if not subset:
        print(name, "done")
        return False  # no change → stop chain

    items = []

    for url in subset:
        if url in existing:
            progress[name] = progress.get(name, 0) + 1
            continue

        try:
            html_text = fetch(url)
            title, thumb, pub = extract(html_text, url)

            media = ""
            if thumb:
                media = f'<media:content url="{html.escape(thumb)}" medium="image" />'

            item = f"""
<item>
<title>{html.escape(title)}</title>
<link>{url}</link>
<guid>{url}</guid>
<pubDate>{format_datetime(pub)}</pubDate>
{media}
</item>
"""
            items.append(item)

            progress[name] = progress.get(name, 0) + 1

            print(name, progress[name], "/", len(urls))

            time.sleep(DELAY)

        except Exception as e:
            print("ERR", url, e)

    # append items
    if items:
        if os.path.exists(path):
            old = open(path, encoding="utf-8").read()
            old = old.replace("</channel>\n</rss>", "")
        else:
            old = f"""<?xml version="1.0" encoding="UTF-8" ?>
<rss version="2.0"
 xmlns:media="http://search.yahoo.com/mrss/">
<channel>
<title>{html.escape(name)}</title>
<link>https://example.com/</link>
<description>Generated feed</description>
"""

        with open(path, "w", encoding="utf-8") as f:
            f.write(old + "".join(items) + "\n</channel>\n</rss>")

        return True

    return False


def main():
    groups = parse_input()
    progress = load_progress()

    changed = False

    for name, urls in groups.items():
        start = progress.get(name, 0)
        if build_feed(name, urls, start, progress):
            changed = True

    if changed:
        save_progress(progress)
    else:
        print("Nothing new → chain ends")


if __name__ == "__main__":
    main()
