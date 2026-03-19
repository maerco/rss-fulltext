import feedparser
import httpx
import trafilatura
from flask import Flask, request, Response
from cachetools import TTLCache
from datetime import datetime
import time

app = Flask(__name__)
cache = TTLCache(maxsize=50, ttl=1800)  # 30 minuti di cache

def fetch_full_text(url: str) -> str:
    try:
        resp = httpx.get(url, timeout=10, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0 (RSS fulltext fetcher)"})
        text = trafilatura.extract(resp.text, include_comments=False,
                                   include_tables=True, no_fallback=False)
        return text or ""
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

        content_escaped = content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        items_xml.append(f"""
    <item>
      <title><![CDATA[{title}]]></title>
      <link>{link}</link>
      <pubDate>{pub}</pubDate>
      <description><![CDATA[{content}]]></description>
    </item>""")

    feed_title = feed.feed.get("title", "Full Text Feed")
    result = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
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
```

**`requirements.txt`**
```
flask
feedparser
httpx
trafilatura
cachetools
gunicorn