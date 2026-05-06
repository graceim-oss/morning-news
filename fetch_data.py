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

def fetch_news(query):
    url = 'https://news.google.com/rss/search?q=' + quote(query) + '&hl=ko&gl=KR&ceid=KR:ko'
    try:
        xml = fetch(url)
        return parse_rss(xml)[:10]
    except Exception as e:
        print('뉴스 오류 (' + query[:20] + '): ' + str(e))
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
        return {
            'krw': d.get('krw', 0),
            'chg24h': chg,
            'dir': 'RISING' if chg >= 0 else 'FALLING',
            'sign': '+' if chg >= 0 else '-',
        }
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
                'link': 'https://store.steampowered.com/app/' + appid,
            })
        return items
    except Exception as e:
        print('Steam 오류: ' + str(e))
        return []

def fetch_gamemeca_top():
    try:
        import requests as req
        r = req.get('https://www.gamemeca.com/ranking.php', timeout=15, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'ko-KR,ko;q=0.9',
            'Referer': 'https://www.gamemeca.com/',
        })
        html = r.text
        items = []
        seen = set()

        # 순위 + 게임명 패턴: <td>숫자</td> 다음에 gmview 링크
        # 전체 HTML에서 순위와 gmview 링크를 동시에 찾기
        # 패턴: | 숫자 | ... | [게임명](gmview링크)
        # 순위와 게임명 각각 추출 후 매칭
        all_ranks = re.findall(r'<td[^>]*>[ \t]*(\d+)[ \t]*(?:<span[^>]*>[^<]*</span>)?[ \t]*</td>', html)
        all_games = re.findall(r'href="([^"]*rts=gmview[^"]*)"[^>]*>[ \t]*([^<\n]+?)[ \t]*</a>', html)
        rank_game = [(all_ranks[i], g[0], g[1]) for i, g in enumerate(all_games) if i < len(all_ranks)]

        for rank_str, link, name in rank_game:
            rank = int(rank_str)
            name = name.strip()
            if name and name not in seen and 1 <= rank <= 20:
                seen.add(name)
                items.append({'rank': rank, 'name': name, 'link': link})

        items.sort(key=lambda x: x['rank'])
        print('게임메카 순위 ' + str(len(items)) + '개 수집')
        return items[:20]
    except Exception as e:
        print('게임메카 순위 오류: ' + str(e))
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
    from concurrent.futures import ThreadPoolExecutor, as_completed

    tasks = {
        'news_wemade':       lambda: fetch_news('위메이드 OR 위믹스 OR WEMIX OR 레전드오브이미르 OR 나이트크로우'),
        'news_blockchain':   lambda: fetch_news('블록체인 OR 가상자산 OR NFT OR Web3 OR 코인 OR 스테이블코인'),
        'news_marketing':    lambda: fetch_news('토스 브랜딩 OR 카카오 마케팅 OR 배달의민족 브랜드 OR 쿠팡 마케팅 OR 무신사 브랜딩 OR 브랜드 캠페인 OR 마케팅 인사이트 OR 디자인 트렌드'),
        'news_brand_global': lambda: fetch_news('brand campaign OR brand strategy OR marketing trend 2026 OR brand design OR brand identity'),
        'trend_kr':          lambda: fetch_gtrend('KR'),
        'trend_global':      lambda: fetch_gtrend('US'),
        'steam':             lambda: fetch_steam_top(),
        'gamemeca':          lambda: fetch_gamemeca_top(),
    }

    results = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
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
    }
    trends = {
        'kr':     results.get('trend_kr', []),
        'global': results.get('trend_global', []),
    }
    rankings = {
        'steam':    results.get('steam', []),
        'gamemeca': results.get('gamemeca', []),
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
    print('  게임메카: ' + str(len(rankings['gamemeca'])) + '개')
    print('  뉴스-마케팅: ' + str(len(news['marketing'])) + '개')
    print('  뉴스-글로벌브랜드: ' + str(len(news['brand_global'])) + '개')

if __name__ == '__main__':
    main()
