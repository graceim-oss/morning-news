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
    """Steam 인기 게임 (SteamSpy - 최근 2주 플레이어 기준)"""
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

def fetch_gamemeca_top():
    """게임메카 인기 게임 순위 (국내 온라인/모바일 통합)"""
    try:
        html = fetch('https://www.gamemeca.com/ranking.php', headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0',
            'Accept': 'text/html,application/xhtml+xml',
            'Accept-Language': 'ko-KR,ko;q=0.9',
            'Referer': 'https://www.gamemeca.com/',
        })
        items = []
        seen = set()
        # 게임명 링크 추출 (gmview 링크)
        game_links = re.findall(
            r'href="(https://www\.gamemeca\.com/game\.php\?rts=gmview[^"]+)"[^>]*>([^<
]+?)</a>',
            html
        )
        # 순위 숫자 추출
        ranks = re.findall(r'<td[^>]*>\s*(\d+)\s*(?:<span[^>]*>[^<]*</span>)?\s*</td>', html)

        for i, (link, name) in enumerate(game_links):
            name = name.strip()
            rank = int(ranks[i]) if i < len(ranks) else i + 1
            if name and name not in seen and rank <= 20:
                seen.add(name)
                items.append({'rank': rank, 'name': name, 'link': link})

        items.sort(key=lambda x: x['rank'])
        print(f'게임메카 순위 {len(items)}개 수집')
        return items[:20]
    except Exception as e:
        print(f'게임메카 순위 오류: {e}')
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
        'steam':     fetch_steam_top(),
        'gamemeca':  fetch_gamemeca_top(),
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
    print(f'  Steam: {len(rankings["steam"])}개')
    print(f'  게임메카: {len(rankings["gamemeca"])}개')

if __name__ == '__main__':
    main()
