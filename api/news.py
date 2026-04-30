import os, re, urllib.parse, json
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
import httpx, feedparser

KST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
NAVER_ID  = os.getenv("NAVER_CLIENT_ID", "")
NAVER_SEC = os.getenv("NAVER_CLIENT_SECRET", "")

QUERIES = {
    "wemade":     {"g": "위메이드 OR 위믹스 OR WEMIX", "n": "위메이드"},
    "blockchain": {"g": "블록체인 OR 가상자산 OR NFT OR Web3", "n": "블록체인 가상자산"},
    "marketing":  {"g": "브랜딩 OR 마케팅트렌드 OR 디지털마케팅", "n": "마케팅 트렌드"},
}

def clean(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()

async def google_news(q, n=12):
    url = f"https://news.google.com/rss/search?q={urllib.parse.quote(q)}&hl=ko&gl=KR&ceid=KR:ko"
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers={"User-Agent": UA}) as c:
            r = await c.get(url)
            r.raise_for_status()
        feed = feedparser.parse(r.text)
        return [{"title": clean(e.get("title","")), "link": e.get("link",""),
                 "source": e.get("source",{}).get("title","Google News"),
                 "published": e.get("published",""), "provider": "google"}
                for e in feed.entries[:n]]
    except Exception:
        return []

async def naver_news(q, n=8):
    if not NAVER_ID: return []
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get("https://openapi.naver.com/v1/search/news.json",
                            headers={"X-Naver-Client-Id": NAVER_ID, "X-Naver-Client-Secret": NAVER_SEC},
                            params={"query": q, "display": n, "sort": "date"})
            if r.status_code == 200:
                return [{"title": clean(i.get("title","")),
                         "link": i.get("originallink") or i.get("link",""),
                         "source": "Naver News", "published": i.get("pubDate",""), "provider": "naver"}
                        for i in r.json().get("items",[])]
    except Exception:
        pass
    return []

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        import asyncio
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        cat = qs.get("category", ["wemade"])[0]
        q = QUERIES.get(cat, QUERIES["wemade"])
        g, n = asyncio.run(asyncio.gather(google_news(q["g"]), naver_news(q["n"])))
        seen = {a["link"] for a in n}
        merged = n + [a for a in g if a["link"] not in seen]
        body = json.dumps({
            "updated": datetime.now(KST).strftime("%H:%M"),
            "articles": merged[:14],
            "sources": {"naver": len(n), "google": len(g)},
        }, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
