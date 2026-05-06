import json, re, ssl
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.parse import quote

KST = timezone(timedelta(hours=9))
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

def fetch(url, headers=None):
    req = Request(url, headers=headers or {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': '*/*',
    })
    with urlopen(req, timeout=15, context=_CTX) as r:
        return r.read().decode('utf-8', errors='replace')

def parse_rss(xml):
    items = []
    for m in re.finditer(r'<item[\s>]([\s\S]*?)<\/item>', xml, re.I):
        blk = m.group(1)
        def get(tag, blk=blk):
            t = re.search(fr'<{tag}[^>]*>([\s\S]*?)<\/{tag}>', blk, re.I)
            if not t: return ''
            return re.sub(r'<[^>]+>', '', t.group(1).replace('<![CDATA[','').replace(']]>','')).strip()
        lm = re.search(r'<link>([^<]+)<\/link>', blk)
        items.append({
            'title': get('title'),
            'link': lm.group(1).strip() if lm else '',
            'source': get('source') or get('News:Source') or 'Google News',
            'published': get('pubDate') or '',
        })
    return items

def fetch_news(query):
    url = f'https://news.google.com/rss/search?q={quote(query)}&hl=ko&gl=KR&ceid=KR:ko'
    try:
        xml = fetch(url)
        return parse_rss(xml)[:10]
    except Exception as e:
        print(f'뉴스 오류 ({query}): {e}')
        return []

def fetch_stock(code):
    url = f'https://m.stock.naver.com/api/stock/{code}/basic'
    try:
        text = fetch(url, headers={
            'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)',
            'Referer': 'https://m.stock.naver.com/',
        })
        d = json.loads(text)
        price = int(d.get('closePrice','0').replace(',',''))
        change = int(d.get('compareToPreviousClosePrice','0').replace(',','') or '0')
        ratio = float(d.get('fluctuationsRatio', '0') or '0')
        dir_ = 'RISING' if change > 0 else 'FALLING' if change < 0 else 'STEADY'
        return {
            'price': f'{price:,}',
            'change': f'{abs(change):,}',
            'ratio': f'{abs(ratio):.2f}',
            'dir': dir_,
            'isOpen': d.get('marketStatus') == 'OPEN',
            'sign': '+' if dir_ == 'RISING' else '-' if dir_ == 'FALLING' else '',
        }
    except Exception as e:
        print(f'주가 오류 ({code}): {e}')
        return {'err': '로드 실패'}

def fetch_wemix():
    url = 'https://api.coingecko.com/api/v3/simple/price?ids=wemix-token&vs_currencies=krw,usd&include_24hr_change=true'
    try:
        text = fetch(url)
        d = json.loads(text).get('wemix-token', {})
        chg = d.get('krw_24h_change', 0)
        return {
            'krw': d.get('krw', 0),
            'chg24h': chg,
            'dir': 'RISING' if chg >= 0 else 'FALLING',
            'sign': '+' if chg >= 0 else '-',
        }
    except Exception as e:
        print(f'WEMIX 오류: {e}')
        return {'err': '로드 실패'}

def fetch_gtrend(geo):
    domain = 'co.kr' if geo == 'KR' else 'com'
    url = f'https://trends.google.{domain}/trending/rss?geo={geo}'
    try:
        xml = fetch(url)
        items = parse_rss(xml)[:20]
        vols = re.findall(r'<ht:approx_traffic>([^<]+)<\/ht:approx_traffic>', xml)
        return [{'title': it['title'], 'vol': vols[i] if i < len(vols) else ''} for i, it in enumerate(items)]
    except Exception as e:
        print(f'트렌드 오류 ({geo}): {e}')
        return []

def fetch_steam_top():
    """Steam 인기 게임 (SteamSpy)"""
    try:
        text = fetch('https://steamspy.com/api.php?request=top100in2weeks', headers={
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://steamspy.com/',
        })
        d = json.loads(text)
        items = []
        for i, (appid, info) in enumerate(list(d.items())[:10]):
            items.append({
                'rank': i + 1,
                'name': info.get('name', ''),
                'appid': appid,
                'players_2weeks': info.get('players_2weeks', 0),
                'link': f'https://store.steampowered.com/app/{appid}',
            })
        return items
    except Exception as e:
        print(f'Steam 오류: {e}')
        return []

def fetch_gplay_top(country='kr', lang='ko', chart='TOP_GROSSING'):
    """Google Play 게임 순위 (gplay-scraper)"""
    try:
        from gplay_scraper import GPlayScraper
        scraper = GPlayScraper()
        result = scraper.list_get_fields(
            collection=chart,
            category='GAME',
            fields=['title', 'developer', 'appId', 'score'],
            count=10,
            lang=lang,
            country=country
        )
        items = []
        for i, item in enumerate(result or []):
            items.append({
                'rank': i + 1,
                'name': item.get('title', ''),
                'developer': item.get('developer', ''),
                'appId': item.get('appId', ''),
                'score': round(item.get('score', 0), 1),
                'link': f"https://play.google.com/store/apps/details?id={item.get('appId','')}",
            })
        return items
    except Exception as e:
        print(f'Google Play 순위 오류 ({country}): {e}')
        return []

def fetch_appstore_top(country='kr', chart='topgrossing'):
    """App Store 게임 순위 (app-store-scraper)"""
    try:
        from app_store_scraper import AppStore
        # app-store-scraper로 top charts
        import requests
        url = f'https://rss.applemarketingtools.com/api/v2/{country}/apps/top-free/10/games.json'
        r = requests.get(url, timeout=10)
        d = r.json()
        items = []
        for i, entry in enumerate(d.get('feed', {}).get('results', [])[:10]):
            items.append({
                'rank': i + 1,
                'name': entry.get('name', ''),
                'developer': entry.get('artistName', ''),
                'link': entry.get('url', ''),
            })
        return items
    except Exception as e:
        print(f'App Store 순위 오류 ({country}): {e}')
        return []

def main():
    now = datetime.now(KST).strftime('%H:%M:%S')
    print(f'수집 시작: {now}')

    print('주가 수집 중...')
    stocks = {
        'wemade':     fetch_stock('112040'),
        'wemade_max': fetch_stock('101730'),
        'wemix':      fetch_wemix(),
    }

    print('뉴스 수집 중...')
    news = {
        'wemade':     fetch_news('위메이드 OR 위믹스 OR WEMIX'),
        'blockchain': fetch_news('블록체인 OR 가상자산 OR NFT OR Web3'),
        'marketing':  fetch_news('브랜딩 OR 마케팅트렌드 OR 디지털마케팅'),
    }

    print('트렌드 수집 중...')
    trends = {
        'kr':     fetch_gtrend('KR'),
        'global': fetch_gtrend('US'),
    }

    print('게임 순위 수집 중...')
    rankings = {
        'steam':           fetch_steam_top(),
        'gplay_kr':        fetch_gplay_top('kr', 'ko', 'TOP_GROSSING'),
        'gplay_global':    fetch_gplay_top('us', 'en', 'TOP_GROSSING'),
        'appstore_kr':     fetch_appstore_top('kr'),
        'appstore_global': fetch_appstore_top('us'),
    }

    data = {
        'updated': now,
        'stocks': stocks,
        'news': news,
        'trends': trends,
        'rankings': rankings,
    }

    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f'완료!')
    for k, v in rankings.items():
        print(f'  {k}: {len(v)}개')

if __name__ == '__main__':
    main()
