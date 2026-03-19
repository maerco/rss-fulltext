import feedparser
import httpx
import trafilatura
from flask import Flask, request, Response
from cachetools import TTLCache
from datetime import datetime
from bs4 import BeautifulSoup

app = Flask(__name__)
cache = TTLCache(maxsize=50, ttl=1800)  # 30 minuti di cache

CONTENT_SELECTORS = [
    "article .entry-content",
    "article .post-content",
    "article .article-content",
    ".entry-content",
    ".post-content",
    ".article-content",
    ".article-body",
    ".post-body",
    "article",
    "[itemprop='articleBody']",
]

JUNK_SELECTORS = (
    "script, style, .sharedaddy, .jp-relatedposts, .post-tags, "
    ".post-categories, nav, .navigation, .comments-area, .sidebar, "
    "[class*='related'], [class*='social'], [class*='share'], "
    "[class*='newsletter'], [class*='subscribe'], [class*='widget']"
)

def get_entry_image(entry) -> str:
    media_thumbnail = entry.get("media_thumbnail")
    if media_thumbnail and isinstance(media_thumbnail, list):
        url = media_thumbnail[0].get("url", "")
        if url:
            return url

    media_content = entry.get("media_content")
    if media_content and isinstance(media_content, list):
        url = media_content[0].get("url", "")
        if url and any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
            return url

    enclosures = entry.get("enclosures", [])
    for enc in enclosures:
        if enc.get("type", "").startswith("image/"):
            return enc.get("url", "")

    return ""

def fetch_og_image(soup: BeautifulSoup) -> str:
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"]
    return ""

def fix_lazy_images(soup: BeautifulSoup) -> BeautifulSoup:
    lazy_attrs = ["data-src", "data-lazy-src", "data-original",
                  "data-url", "data-image", "data-hi-res-src"]
    for img in soup.find_all("img"):
        for attr in lazy_attrs:
            val = img.get(attr)
            if val and val.startswith("http"):
                img["src"] = val
                break
        if not img.get("src") or "placeholder" in img.get("src", ""):
            srcset = img.get("srcset") or img.get("data-srcset", "")
            if srcset:
                first_url = srcset.strip().split()[0]
                if first_url.startswith("http"):
                    img["src"] = first_url
    return soup

def extract_with_beautifulsoup(soup: BeautifulSoup) -> str:
    for selector in CONTENT_SELECTORS:
        el = soup.select_one(selector)
        if el:
            for tag in el.select(JUNK_SELECTORS):
                tag.decompose()
            text = el.get_text(strip=True)
            if len(text) > 50:  # soglia bassa: anche articoli brevissimi
                return str(el)
    return ""

def fetch_full_text(url: str, cover_url: str = "") -> str:
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (RSS fulltext fetcher)"})
        soup = BeautifulSoup(resp.text, "html.parser")

        if not cover_url:
            cover_url = fetch_og_image(soup)

        soup = fix_lazy_images(soup)

        # Prima prova con BeautifulSoup diretto (più affidabile per siti con
        # articoli brevi che trafilatura tende a scartare)
        content = extract_with_beautifulsoup(soup)

        # Se BeautifulSoup non trova niente, prova trafilatura come fallback
        if not content:
            content = trafilatura.extract(
                str(soup),
                output_format="html",
                include_comments=False,
                include_tables=True,
                include_images=True,
                no_fallback=False
            ) or ""

        # Aggiunge copertina in cima se non già presente nel contenuto
        if content and cover_url and cover_url not in content:
            cover_tag = f'<img src="{cover_url}" style="max-width:100%;margin-bottom:1em;" />'
            content = cover_tag + content

        return content or ""
    except Exception:
        return ""

def build_full_feed(feed_url: str, force_refresh: bool = False) -> str:
    if not force_refresh and feed_url in cache:
        return cache[feed_url]

    feed = feedparser.parse(feed_url)

    items_xml = []
    for entry in feed.entries[:20]:
        title = entry.get("title", "")
        link  = entry.get("link", "")
        pub   = entry.get("published",
                          datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000"))

        cover_url = get_entry_image(entry)

        existing = entry.get("content", [{}])[0].get("value", "") or entry.get("summary", "")
        existing_text = BeautifulSoup(existing, "html.parser").get_text(strip=True)

        # Scrapa sempre: anche se il feed ha del testo, potrebbe essere troncato.
        # Usiamo il contenuto del feed solo se lo scraping fallisce completamente.
        scraped = fetch_full_text(link, cover_url)
        content = scraped if scraped else existing

        # Se il feed ha un'immagine e non è già nel contenuto, aggiungila
        if cover_url and cover_url not in content:
            cover_tag = f'<img src="{cover_url}" style="max-width:100%;margin-bottom:1em;" />'
            content = cover_tag + content

        plain_text = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
        summary = plain_text[:300] + "..." if len(plain_text) > 300 else plain_text

        items_xml.append(f"""
    <item>
      <title><![CDATA[{title}]]></title>
      <link>{link}</link>
      <pubDate>{pub}</pubDate>
      <description><![CDATA[{summary}]]></description>
      <content:encoded><![CDATA[{content}]]></content:encoded>
    </item>""")

    feed_title = feed.feed.get("title", "Full Text Feed")
    result = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>{feed_title} (Full Text)</title>
    <link>{feed.feed.get('link', feed_url)}</link>
    <description>Full text feed generato da rss-fulltext</description>
    {''.join(items_xml)}
  </channel>
</rss>"""

    cache[feed_url] = result
    return result

@app.route("/")
def index():
    return """
    <h2>RSS Full Text Service</h2>
    <p>Uso: <code>/feed?url=https://example.com/feed.xml</code></p>
    <p>Forza aggiornamento cache: <code>/feed?url=https://example.com/feed.xml&amp;refresh=1</code></p>
    """

@app.route("/feed")
def full_feed():
    url = request.args.get("url")
    force_refresh = request.args.get("refresh", "0") == "1"
    if not url:
        return Response("Parametro ?url= mancante", status=400)
    try:
        xml = build_full_feed(url, force_refresh)
        return Response(xml, mimetype="application/rss+xml")
    except Exception as e:
        return Response(f"Errore: {str(e)}", status=500)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
