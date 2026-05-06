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
    """Steam 실시간 인기 게임 (동시접속자 기준)"""
    url = 'https://store.steampowered.com/api/featuredcategories?cc=KR&l=koreana'
    try:
        text = fetch(url)
        d = json.loads(text)
        items = []
        # top_sellers 카테고리
        for item in d.get('top_sellers', {}).get('items', [])[:10]:
            items.append({
                'rank': len(items) + 1,
                'name': item.get('name', ''),
                'appid': item.get('id', ''),
                'price': item.get('final_price', 0),
                'discount': item.get('discount_percent', 0),
                'link': f"https://store.steampowered.com/app/{item.get('id','')}",
            })
        return items
    except Exception as e:
        print(f'Steam 오류: {e}')
        # fallback: Steam 인기 게임 API
        try:
            url2 = 'https://store.steampowered.com/api/featured/?cc=KR&l=koreana'
            text2 = fetch(url2)
            d2 = json.loads(text2)
            items = []
            for item in d2.get('featured_win', [])[:10]:
                items.append({
                    'rank': len(items) + 1,
                    'name': item.get('name', ''),
                    'appid': item.get('id', ''),
                    'price': item.get('final_price', 0),
                    'discount': item.get('discount_percent', 0),
                    'link': f"https://store.steampowered.com/app/{item.get('id','')}",
                })
            return items
        except Exception as e2:
            print(f'Steam fallback 오류: {e2}')
            return []

def fetch_google_play_top():
    """Google Play 한국 인기 게임"""
    # Google Play RSS (비공식이지만 안정적)
    url = 'https://androidrank.org/listapps?category=GAME&start=1&price=all&region=kr&sort=4&chart=topselling_free&json=1'
    try:
        text = fetch(url)
        d = json.loads(text)
        items = []
        for i, entry in enumerate(d[:10]):
            items.append({
                'rank': i + 1,
                'name': entry.get('title', ''),
                'developer': entry.get('developer', ''),
                'link': 'https://play.google.com/store/apps/details?id=' + entry.get('id',''),
            })
        if items:
            return items
    except Exception as e:
        print(f'Google Play androidrank 오류: {e}')
    # fallback: Google Play RSS
    try:
        rss_url = 'https://play.google.com/store/apps/collection/topselling_free_games?hl=ko&gl=KR'
        # Apple RSS로 Google Play 순위 대체 (같은 한국 시장)
        url2 = 'https://rss.applemarketingtools.com/api/v2/kr/apps/top-free/10/games.json'
        text = fetch(url2)
        d = json.loads(text)
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
        print(f'Google Play 순위 오류: {e}')
        return []

def fetch_appstore_top():
    """App Store 한국 인기 게임"""
    urls = [
        'https://rss.applemarketingtools.com/api/v2/kr/apps/top-free/10/games.json',
        'https://itunes.apple.com/kr/rss/topfreegames/limit=10/json',
    ]
    for url in urls:
        try:
            text = fetch(url)
            d = json.loads(text)
            # applemarketingtools 형식
            results = d.get('feed', {}).get('results', [])
            if not results:
                # itunes 형식
                results = d.get('feed', {}).get('entry', [])
            items = []
            for i, entry in enumerate(results[:10]):
                name = entry.get('name') or entry.get('im:name', {}).get('label', '')
                developer = entry.get('artistName') or entry.get('im:artist', {}).get('label', '')
                link = entry.get('url') or entry.get('id', {}).get('label', '')
                items.append({
                    'rank': i + 1,
                    'name': name,
                    'developer': developer,
                    'link': link,
                })
            if items:
                return items
        except Exception as e:
            print(f'App Store 순위 오류: {e}')
    return []

def fetch_steam_concurrent():
    """Steam 실시간 동시접속자 Top 10"""
    url = 'https://store.steampowered.com/api/featuredcategories/?cc=KR&l=koreana'
    try:
        # Steam Spy API (공개)
        url2 = 'https://steamspy.com/api.php?request=top100in2weeks'
        text = fetch(url2)
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
        print(f'Steam 동시접속 오류: {e}')
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
        'steam':       fetch_steam_concurrent(),
        'appstore':    fetch_appstore_top(),
        'googleplay':  fetch_google_play_top(),
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

    print(f'완료! data.json 저장됨')
    print(f'  Steam: {len(rankings["steam"])}개')
    print(f'  App Store: {len(rankings["appstore"])}개')
    print(f'  Google Play: {len(rankings["googleplay"])}개')

if __name__ == '__main__':
    main()
