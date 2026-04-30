import json, asyncio
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
import httpx

KST = timezone(timedelta(hours=9))
MOB_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

STOCKS = [
    {"code": "112040", "name": "위메이드",     "market": "KOSDAQ"},
    {"code": "233180", "name": "위메이드맥스", "market": "KOSDAQ"},
]

async def naver_stock(code):
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True,
                                      headers={"User-Agent": MOB_UA, "Referer": "https://m.stock.naver.com"}) as c:
            r = await c.get(f"https://m.stock.naver.co
cat > api/prices.py << 'PYEOF'
import json, asyncio
from http.server import BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta
import httpx

KST = timezone(timedelta(hours=9))
MOB_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36"

STOCKS = [
    {"code": "112040", "name": "위메이드",     "market": "KOSDAQ"},
    {"code": "233180", "name": "위메이드맥스", "market": "KOSDAQ"},
]

async def naver_stock(code):
    try:
        async with httpx.AsyncClient(timeout=6, follow_redirects=True,
                                      headers={"User-Agent": MOB_UA, "Referer": "https://m.stock.naver.com"}) as c:
            r = await c.get(f"https://m.stock.naver.com/api/stock/{code}/basic")
            if r.status_code == 409:
                return {"error": "거래정지"}
            d = r.json()
            direction = d.get("compareToPreviousPrice", {}).get("name", "STEADY")
            sign = "+" if direction == "RISING" else ("-" if direction == "FALLING" else "")
            return {
                "price": d.get("closePrice", "—"),
                "change": d.get("compareToPreviousClosePrice", "0"),
                "ratio": d.get("fluctuationsRatio", "0.00"),
                "direction": direction, "sign": sign,
                "isOpen": d.get("marketStatus") == "OPEN",
                "naverUrl": f"https://finance.naver.com/item/main.naver?code={code}",
            }
    except Exception as e:
        return {"error": str(e)[:60]}

async def wemix_price():
    try:
        async with httpx.AsyncClient(timeout=6, headers={"User-Agent": UA}) as c:
            r = await c.get("https://api.coingecko.com/api/v3/simple/price?ids=wemix-token&vs_currencies=krw,usd&include_24hr_change=true")
            r.raise_for_status()
            d = r.json().get("wemix-token", {})
            chg = d.get("krw_24h_change", 0)
            return {
                "price_krw": f"{d.get('krw', 0):,.2f}",
                "change_24h": f"{'+' if chg >= 0 else ''}{chg:.2f}",
                "direction": "RISING" if chg >= 0 else "FALLING",
                "sign": "+" if chg >= 0 else "-",
                "cgUrl": "https://www.coingecko.com/en/coins/wemix-token",
            }
    except Exception as e:
        return {"error": str(e)[:60]}

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        tasks = [naver_stock(s["code"]) for s in STOCKS]
        results = asyncio.run(asyncio.gather(*tasks, wemix_price()))
        stocks = [{**s, **results[i]} for i, s in enumerate(STOCKS)]
        body = json.dumps({"updated": datetime.now(KST).strftime("%H:%M:%S"), "stocks": stocks, "wemix": results[-1]}, ensure_ascii=False).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *a): pass
