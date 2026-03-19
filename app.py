import feedparser
import httpx
import trafilatura
from flask import Flask, request, Response
from cachetools import TTLCache
from datetime import datetime
from bs4 import BeautifulSoup

app = Flask(__name__)
cache = TTLCache(maxsize=50, ttl=1800)  # 30 minuti di cache

def fetch_og_image(soup: BeautifulSoup) -> str:
    """Estrae l'immagine di copertina dai meta tag og:image."""
    og = soup.find("meta", property="og:image")
    if og and og.get("content"):
        return f'<img src="{og["content"]}" style="max-width:100%;margin-bottom:1em;" />'
    return ""

def fetch_full_text(url: str) -> str:
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (RSS fulltext fetcher)"})
        soup = BeautifulSoup(resp.text, "html.parser")
        og_image = fetch_og_image(soup)

        content = trafilatura.extract(
            resp.text,
            output_format="html",
            include_comments=False,
            include_tables=True,
            include_images=True,
            no_fallback=False
        )

        if content and og_image:
            # Inserisce la copertina prima del testo se non è già presente
            if og_image.split('src="')[1].split('"')[0] not in content:
                content = og_image + content

        return content or ""
    except Exception:
        return ""

def build_full_feed(feed_url: str) -> str:
    if feed_url in cache:
        return cache[feed_url]

    feed = feedparser.parse(feed_url)

    items_xml = []
    for entry in feed.entries[:20]:  # max 20 articoli
        title   = entry.get("title", "")
        link    = entry.get("link", "")
        pub     = entry.get("published", datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S +0000"))

        # Controlla se il contenuto è già completo (> 500 caratteri)
        existing = entry.get("content", [{}])[0].get("value", "") or entry.get("summary", "")
        if len(existing) > 500:
            content = existing
        else:
            content = fetch_full_text(link) or existing

        # Sommario breve per <description> (primi 300 caratteri del testo)
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
