import json, re, asyncio, urllib.parse
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
from collections import Counter
from urllib.parse import unquote
import httpx, feedparser

KST = timezone(timedelta(hours=9))
UA  = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"
SKIP_NS = ("사용자:", "나무위키:", "파일:", "틀:", "분류:", "위키프로젝트:", "토론:")

async def google_trends():
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True, headers={"User-Agent": UA}) as c:
            r = await c.get("https://trends.google.co.kr/trending/rss?geo=KR")
            r.raise_for_status()
        feed = feedparser.parse(r.text)
        return [{"rank": i+1, "keyword": e.get("title",""), "traffic": e.get("ht_approx_traffic","")}
                for i, e in enumerate(feed.entries[:20])]
    except Exception:
        return []

async def namu_trending():
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True,
                                      headers={"User-Agent": UA, "Accept-Language": "ko-KR,ko;q=0.9"}) as c:
            r = await c.get("https://namu.wiki/RecentChanges")
            r.raise_for_status()
        src = r.text
        entries = re.findall(
            r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}).{0,600}?href=\"/w/([^\"?#]+)\"",
            src, re.DOTALL)
        filtered = []
        for ts, raw in entries:
            try: title = unquote(raw)
            except: title = raw
            if any(title.startswith(ns) for ns in SKIP_NS) or len(title) < 2:
                continue
            filtered.append((ts, title))
        counter = Counter(t for _, t in filtered)
        seen, result, rank = set(), [], 1
        for title, cnt in counter.most_common(15):
            if title in seen: continue
            seen.add(title)
            times = [ts for ts, t in filtered if t == title]
            result.append({"rank": rank, "title": title, "edits": cnt,
                           "latest": times[0] if times else "",
                           "url": f"https://namu.wiki/w/{title}"})
            rank += 1
        return result
    except Exception:
        return []

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        qs  = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        src = qs.get("src", ["google"])[0]
        if src == "namu":
            data = asyncio.run(namu_trending())
            body = json.dumps({"updated": datetime.now(KST).strftime("%H:%M"), "items": data}, ensure_ascii=False).encode()
        else:
            data = asyncio.run(google_trends())
            body = json.dumps({"updated": datetime.now(KST).strftime("%H:%M"), "trends": data}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
