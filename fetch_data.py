import json, re, ssl
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

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
            t = re.search('<' + tag + '[^>]*>([\\s\\S]*?)<\\/' + tag + '>', blk, re.I)
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

def fetch_news_en(query):
    url = 'https://news.google.com/rss/search?q=' + quote(query) + '&hl=en&gl=US&ceid=US:en'
    try:
        xml = fetch(url)
        return parse_rss(xml)[:10]
    except Exception as e:
        print('영문뉴스 오류: ' + str(e))
        return []

def fetch_news(query):
    url = 'https://news.google.com/rss/search?q=' + quote(query) + '&hl=ko&gl=KR&ceid=KR:ko'
    try:
        xml = fetch(url)
        return parse_rss(xml)[:10]
    except Exception as e:
        print('뉴스 오류: ' + str(e))
        return []

def fetch_stock(code):
    url = 'https://m.stock.naver.com/api/stock/' + code + '/basic'
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
            'price': '{:,}'.format(price),
            'change': '{:,}'.format(abs(change)),
            'ratio': '{:.2f}'.format(abs(ratio)),
            'dir': dir_,
            'isOpen': d.get('marketStatus') == 'OPEN',
            'sign': '+' if dir_ == 'RISING' else '-' if dir_ == 'FALLING' else '',
        }
    except Exception as e:
        print('주가 오류 (' + code + '): ' + str(e))
        return {'err': '로드 실패'}

def fetch_wemix():
    url = 'https://api.coingecko.com/api/v3/simple/price?ids=wemix-token&vs_currencies=krw,usd&include_24hr_change=true'
    try:
        text = fetch(url)
        d = json.loads(text).get('wemix-token', {})
        chg = d.get('krw_24h_change', 0)
        return {'krw': d.get('krw', 0), 'chg24h': chg,
                'dir': 'RISING' if chg >= 0 else 'FALLING',
                'sign': '+' if chg >= 0 else '-'}
    except Exception as e:
        print('WEMIX 오류: ' + str(e))
        return {'err': '로드 실패'}

def fetch_gtrend(geo):
    domain = 'co.kr' if geo == 'KR' else 'com'
    url = 'https://trends.google.' + domain + '/trending/rss?geo=' + geo
    try:
        xml = fetch(url)
        items = parse_rss(xml)[:20]
        vols = re.findall(r'<ht:approx_traffic>([^<]+)<\/ht:approx_traffic>', xml)
        return [{'title': it['title'], 'vol': vols[i] if i < len(vols) else ''} for i, it in enumerate(items)]
    except Exception as e:
        print('트렌드 오류 (' + geo + '): ' + str(e))
        return []

def fetch_steam_top():
    try:
        text = fetch('https://steamspy.com/api.php?request=top100in2weeks', headers={
            'User-Agent': 'Mozilla/5.0', 'Referer': 'https://steamspy.com/',
        })
        d = json.loads(text)
        items = []
        for i, (appid, info) in enumerate(list(d.items())[:10]):
            items.append({
                'rank': i + 1, 'name': info.get('name', ''), 'appid': appid,
                'players_2weeks': info.get('players_2weeks', 0),
                'link': 'https://store.steampowered.com/app/' + appid,
            })
        return items
    except Exception as e:
        print('Steam 오류: ' + str(e))
        return []

def fetch_gametrics_top():
    try:
        import requests as req
        r = req.get('https://www.gametrics.com/rank/Rank02.aspx', timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0',
            'Accept': 'text/html', 'Accept-Language': 'ko-KR,ko;q=0.9',
            'Referer': 'https://www.gametrics.com/',
        })
        html = r.text
        items = []
        seen = set()
        rows = re.findall(r'<tr[^>]*>([\s\S]*?)</tr>', html, re.I)
        for row in rows:
            rank_m = re.search(r'<td[^>]*>\s*(\d+)\s*</td>', row)
            game_m = re.search(r'href="([^"]*GameInfo[^"]*)"[^>]*>([^<]+)</a>', row, re.I)
            pct_m = re.search(r'(\d+\.\d+)%', row)
            if rank_m and game_m:
                rank = int(rank_m.group(1))
                name = game_m.group(2).strip()
                link = 'https://www.gametrics.com' + game_m.group(1) if game_m.group(1).startswith('/') else game_m.group(1)
                pct = pct_m.group(1) if pct_m else ''
                if name and name not in seen and 1 <= rank <= 20:
                    seen.add(name)
                    items.append({'rank': rank, 'name': name, 'link': link, 'pct': pct})
        items.sort(key=lambda x: x['rank'])
        print('게임트릭스 순위 ' + str(len(items)) + '개 수집')
        return items[:20]
    except Exception as e:
        print('게임트릭스 순위 오류: ' + str(e))
        return []

def fetch_gplay_top(country='kr', lang='ko', chart='TOP_GROSSING'):
    try:
        from gplay_scraper import GPlayScraper
        scraper = GPlayScraper()
        result = scraper.list_get_fields(
            collection=chart, category='GAME',
            fields=['title', 'developer', 'appId', 'score'],
            count=10, lang=lang, country=country
        )
        items = []
        for i, item in enumerate(result or []):
            items.append({
                'rank': i + 1, 'name': item.get('title', ''),
                'developer': item.get('developer', ''),
                'link': 'https://play.google.com/store/apps/details?id=' + item.get('appId',''),
            })
        print('Google Play (' + country + ') ' + str(len(items)) + '개 수집')
        return items
    except Exception as e:
        print('Google Play 순위 오류 (' + country + '): ' + str(e))
        return []

def fetch_appstore_top(country='kr'):
    try:
        import requests as req
        urls = [
            'https://rss.marketingtools.apple.com/api/v2/' + country + '/apps/top-grossing/10/games.json',
            'https://rss.applemarketingtools.com/api/v2/' + country + '/apps/top-grossing/10/games.json',
        ]
        for url in urls:
            try:
                r = req.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'})
                if r.status_code != 200:
                    continue
                d = r.json()
                results = d.get('feed', {}).get('results', [])
                items = []
                for i, entry in enumerate(results[:10]):
                    name = entry.get('name', '')
                    if name:
                        items.append({'rank': i+1, 'name': name,
                                     'developer': entry.get('artistName', ''),
                                     'link': entry.get('url', '')})
                if items:
                    print('App Store (' + country + ') ' + str(len(items)) + '개 수집')
                    return items
            except Exception as e2:
                print('App Store URL 오류: ' + str(e2))
        return []
    except Exception as e:
        print('App Store 오류: ' + str(e))
        return []

def main():
    now = datetime.now(KST).strftime('%H:%M:%S')
    print('수집 시작: ' + now)

    print('주가 수집 중...')
    stocks = {
        'wemade':     fetch_stock('112040'),
        'wemade_max': fetch_stock('101730'),
        'wemix':      fetch_wemix(),
    }

    print('뉴스/트렌드/순위 병렬 수집 중...')
    tasks = {
        'news_wemade':       lambda: fetch_news('위메이드 OR 위믹스 OR WEMIX OR 레전드오브이미르 OR 나이트크로우'),
        'news_blockchain':   lambda: fetch_news('블록체인 OR 가상자산 OR NFT OR Web3 OR 코인 OR 스테이블코인'),
        'news_marketing':    lambda: fetch_news('브랜드 마케팅 OR 브랜드 캠페인 OR 광고 캠페인 OR 마케팅 트렌드 OR 브랜드 전략 OR 콘텐츠 마케팅 OR SNS 마케팅 OR 인플루언서 마케팅 when:1d'),
        'news_brand_global': lambda: fetch_news_en('brand campaign 2026 OR global marketing trend OR brand identity OR viral campaign OR advertising design when:7d'),
        'trend_kr':          lambda: fetch_gtrend('KR'),
        'trend_global':      lambda: fetch_gtrend('US'),
        'steam':             lambda: fetch_steam_top(),
        'gametrics':         lambda: fetch_gametrics_top(),
        'gplay_kr':          lambda: fetch_gplay_top('kr', 'ko', 'TOP_GROSSING'),
        'appstore_kr':       lambda: fetch_appstore_top('kr'),
    }

    results = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        future_map = {executor.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(future_map):
            key = future_map[future]
            try:
                results[key] = future.result()
            except Exception as e:
                print(key + ' 오류: ' + str(e))
                results[key] = []

    news = {
        'wemade':       results.get('news_wemade', []),
        'blockchain':   results.get('news_blockchain', []),
        'marketing':    results.get('news_marketing', []),
        'brand_global': results.get('news_brand_global', []),
        'aiit':         results.get('news_aiit', []),
    }
    trends = {
        'kr':     results.get('trend_kr', []),
        'global': results.get('trend_global', []),
    }
    rankings = {
        'steam':       results.get('steam', []),
        'gametrics':   results.get('gametrics', []),
        'gplay_kr':    results.get('gplay_kr', []),
        'appstore_kr': results.get('appstore_kr', []),
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

    print('완료!')
    print('  Steam: ' + str(len(rankings['steam'])) + '개')
    print('  게임트릭스: ' + str(len(rankings['gametrics'])) + '개')
    print('  Google Play KR: ' + str(len(rankings['gplay_kr'])) + '개')
    print('  App Store KR: ' + str(len(rankings['appstore_kr'])) + '개')
    print('  뉴스-마케팅: ' + str(len(news['marketing'])) + '개')
    print('  뉴스-글로벌브랜드: ' + str(len(news['brand_global'])) + '개')
    print('  뉴스-AI/IT: ' + str(len(news['aiit'])) + '개')

if __name__ == '__main__':
    main()
