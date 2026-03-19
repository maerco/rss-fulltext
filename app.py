import feedparser
import httpx
import trafilatura
from flask import Flask, request, Response
from cachetools import TTLCache
from datetime import datetime
from bs4 import BeautifulSoup

app = Flask(__name__)
cache = TTLCache(maxsize=50, ttl=1800)  # 30 minuti di cache

def get_entry_image(entry) -> str:
    """Estrae l'immagine dall'entry del feed (media:thumbnail, enclosure, og:image)."""
    # 1. media:thumbnail (Wired e molti altri)
    media_thumbnail = entry.get("media_thumbnail")
    if media_thumbnail and isinstance(media_thumbnail, list):
        url = media_thumbnail[0].get("url", "")
        if url:
            return url

    # 2. media:content con url
    media_content = entry.get("media_content")
    if media_content and isinstance(media_content, list):
        url = media_content[0].get("url", "")
        if url and any(ext in url.lower() for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif"]):
            return url

    # 3. enclosure (podcast/standard RSS)
    enclosures = entry.get("enclosures", [])
    for enc in enclosures:
        if enc.get("type", "").startswith("image/"):
            return enc.get("url", "")

    return ""

def fetch_og_image(soup: BeautifulSoup) -> str:
    """Fallback: estrae og:image dalla pagina."""
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return og["content"]
    return ""

def fix_lazy_images(soup: BeautifulSoup) -> BeautifulSoup:
    """Sostituisce attributi lazy-load con src standard."""
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

def fetch_full_text(url: str, cover_url: str = "") -> str:
    """Scarica la pagina ed estrae il testo completo in HTML."""
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (RSS fulltext fetcher)"})
        soup = BeautifulSoup(resp.text, "html.parser")

        # Fallback og:image se non abbiamo già un'immagine dal feed
        if not cover_url:
            cover_url = fetch_og_image(soup)

        soup = fix_lazy_images(soup)
        fixed_html = str(soup)

        content = trafilatura.extract(
            fixed_html,
            output_format="html",
            include_comments=False,
            include_tables=True,
            include_images=True,
            no_fallback=False
        )

        # Prepend immagine di copertina se disponibile e non già presente
        if content and cover_url and cover_url not in content:
            cover_tag = f'<img src="{cover_url}" style="max-width:100%;margin-bottom:1em;" />'
            content = cover_tag + content

        return content or ""
    except Exception:
        return ""

def build_full_feed(feed_url: str) -> str:
    if feed_url in cache:
        return cache[feed_url]

    feed = feedparser.parse(feed_url)

    items_xml = []
    for entry in feed.entries[:20]:
        title = entry.get("title", "")
        link  = entry.get("link", "")
        pub   = entry.get("published",
                          datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000"))

        # Immagine dal feed (media:thumbnail ecc.)
        cover_url = get_entry_image(entry)

        # Contenuto: se già completo (> 500 chars) lo usiamo, altrimenti scarichiamo
        existing = entry.get("content", [{}])[0].get("value", "") or entry.get("summary", "")
        if len(existing) > 500:
            content = existing
            # Aggiunge comunque la copertina se non è già nell'HTML
            if cover_url and cover_url not in content:
                cover_tag = f'<img src="{cover_url}" style="max-width:100%;margin-bottom:1em;" />'
                content = cover_tag + content
        else:
            content = fetch_full_text(link, cover_url) or existing

        # Sommario testuale per <description>
        soup_content = BeautifulSoup(content, "html.parser")
        plain_text = soup_content.get_text(" ", strip=True)
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
    """

@app.route("/feed")
def full_feed():
    url = request.args.get("url")
    if not url:
        return Response("Parametro ?url= mancante", status=400)
    try:
        xml = build_full_feed(url)
        return Response(xml, mimetype="application/rss+xml")
    except Exception as e:
        return Response(f"Errore: {str(e)}", status=500)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
