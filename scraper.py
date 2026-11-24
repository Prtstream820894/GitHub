import os
import re
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

BASE_URL = "https://new.touchcric.com/"
PROXY_BASE = os.environ.get("PROXY_BASE", "").rstrip("/")


def wrap_proxy(m3u8_url: str, referer: str) -> str:
    if not PROXY_BASE:
        return m3u8_url
    return f"{PROXY_BASE}?url={quote(m3u8_url, safe='')}&referer={quote(referer, safe='')}"


def get_live_matches(page):
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    soup = BeautifulSoup(page.content(), "html.parser")
    matches = []

    for link in soup.find_all("a", href=True):
        href = urljoin(BASE_URL, link["href"])
        text = " ".join(link.get_text(" ", strip=True).split())
        img = link.find("img")
        logo = urljoin(BASE_URL, img["src"]) if img and img.get("src") else ""
        if text and href != BASE_URL and len(text) > 4:
            matches.append({"title": text, "logo": logo, "href": href})

    # Deduplicate by href
    seen = set()
    unique = []
    for m in matches:
        if m["href"] not in seen:
            seen.add(m["href"])
            unique.append(m)
    return unique


def extract_m3u8_from_match(page, match_url: str) -> str | None:
    found = []

    def on_request(req):
        if ".m3u8" in req.url:
            found.append(req.url)

    page.on("request", on_request)
    try:
        page.goto(match_url, wait_until="domcontentloaded", timeout=25000)
        page.wait_for_timeout(6000)
        for frame in page.frames:
            try:
                html = frame.content()
                for m in re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html):
                    found.append(m)
            except Exception:
                pass
    except Exception:
        pass
    finally:
        page.remove_listener("request", on_request)

    return found[0] if found else None


def main():
    lines = ["#EXTM3U"]
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        matches = get_live_matches(page)
        for m in matches[:10]:
            m3u8 = extract_m3u8_from_match(page, m["href"])
            if m3u8:
                stream_url = wrap_proxy(m3u8, m["href"])
                lines.append(
                    f'#EXTINF:-1 tvg-logo="{m["logo"]}" group-title="Touchcric Live",{m["title"]}'
                )
                lines.append(stream_url)

        browser.close()

    if len(lines) > 1:
        with open("playlist.m3u", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
