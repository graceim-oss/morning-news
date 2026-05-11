import json, re, ssl, html as _html, os
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed

KST = timezone(timedelta(hours=9))
_CTX = ssl.create_default_context()
_BASE = os.path.dirname(os.path.abspath(__file__))
SOURCES_FILE = os.path.join(_BASE, 'newsletter-admin', 'sources.json')
PENDING_FILE = os.path.join(_BASE, 'pending_articles.json')
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
        raw_desc = get('description')
        clean_desc = re.sub(r'<[^>]+>', '', _html.unescape(raw_desc)).strip() if raw_desc else ''
        items.append({
            'title': get('title'),
            'link': lm.group(1).strip() if lm else '',
            'source': get('source') or get('News:Source') or 'Google News',
            'published': get('pubDate') or '',
            'description': clean_desc,
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

def fetch_marketing_news():
    ko = fetch_news('브랜드 캠페인 OR 마케팅 트렌드 OR 브랜드 전략 OR 광고 캠페인 OR 콘텐츠 마케팅 when:7d')
    en = fetch_news_en('brand campaign OR marketing trend OR brand strategy OR creative advertising 2026 when:7d')
    combined = ko + en
    seen = set()
    result = []
    for item in combined:
        if item['link'] not in seen:
            seen.add(item['link'])
            result.append(item)
    print('마케팅 클리핑 ' + str(len(result[:5])) + '개 수집')
    return result[:5]

# ── Section 1 소스 ────────────────────────────────────────────────────────────

def fetch_brand_insight_ko():
    items = fetch_news('브랜드 마케팅 OR 마케팅 인사이트 OR 캠페인 성공사례 OR 브랜드 전략 OR 광고 트렌드 when:7d')
    print('브랜드인사이트(KR) ' + str(len(items)) + '개 수집')
    return items

def fetch_brand_insight_global():
    items = fetch_news_en('brand marketing strategy OR marketing insight OR brand campaign success OR creative brand 2026 when:7d')
    print('브랜드인사이트(글로벌) ' + str(len(items)) + '개 수집')
    return items

# ── Section 3 카테고리별 뉴스 ─────────────────────────────────────────────────

def fetch_s3_ai():
    items = fetch_news('ChatGPT OR Gemini OR LLM OR 생성형AI OR AI서비스 when:2d')
    print('S3-AI ' + str(len(items)) + '개 수집')
    return items

def fetch_s3_game():
    items = fetch_news('게임트렌드 OR 게임마케팅 OR 게임IP OR 모바일게임 when:2d')
    print('S3-게임 ' + str(len(items)) + '개 수집')
    return items

def fetch_s3_wemade():
    items = fetch_news('Wemade OR 위메이드 OR WEMIX OR 나이트크로우 OR 이미르 when:2d')
    print('S3-위메이드 ' + str(len(items)) + '개 수집')
    return items

def fetch_s3_blockchain():
    items = fetch_news('블록체인게임 OR Web3 OR NFT게임 OR P2E when:2d')
    print('S3-블록체인 ' + str(len(items)) + '개 수집')
    return items

def _dedup(items):
    seen = set()
    result = []
    for item in items:
        key = item.get('link', '') or item.get('title', '')
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result

def load_sources():
    try:
        with open(SOURCES_FILE, encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print('WARNING: sources.json 로드 실패 - ' + str(e))
        return None

def fetch_section_generic(sec_id, queries):
    all_items = []
    for q in queries:
        if not q.get('enabled', True):
            continue
        lang = q.get('lang', 'ko')
        query_str = q.get('q', '')
        items = fetch_news_en(query_str) if lang == 'en' else fetch_news(query_str)
        all_items.extend(items)
    result = _dedup(all_items)[:5]
    if not result:
        print('WARNING: ' + sec_id + ' 수집 결과 0건')
    else:
        print(sec_id + ' ' + str(len(result)) + '개 수집')
    return result

# ── Dashboard 5-section 소스 ──────────────────────────────────────────────────

def fetch_s1_game_trend():
    ko = fetch_news('게임 트렌드 OR 글로벌 게임 마케팅 OR 라이브서비스 운영 when:7d')
    en = fetch_news_en('game industry trend OR live service game OR gaming content creator 2026 when:7d')
    items = _dedup(ko + en)[:5]
    print('S1-게임트렌드 ' + str(len(items)) + '개 수집')
    return items

def fetch_s2_consumer():
    ko = fetch_news('MZ세대 소비 OR 굿즈 OR 팬덤 소비 OR 캐릭터 콜라보 when:7d')
    en = fetch_news_en('gen z consumer trend OR fandom merch OR brand collaboration 2026 when:7d')
    items = _dedup(ko + en)[:5]
    print('S2-소비트렌드 ' + str(len(items)) + '개 수집')
    return items

def fetch_s3_nextgen():
    ko = fetch_news('알파세대 OR Z세대 SNS OR 숏폼 트렌드 OR 밈 when:7d')
    en = fetch_news_en('alpha generation OR gen z platform OR shortform content trend 2026 when:7d')
    items = _dedup(ko + en)[:5]
    print('S3-넥스트젠 ' + str(len(items)) + '개 수집')
    return items

def fetch_s4_lygl():
    items = fetch_news('레전드오브이미르 OR Legend of YMIR when:7d')
    if not items:
        items = fetch_news_en('Legend of YMIR game when:14d')
    print('S4-LYGL ' + str(len(items)) + '개 수집')
    return items[:5]

def fetch_s4_ncgl():
    items = fetch_news('나이트크로우 OR Night Crows when:7d')
    if not items:
        items = fetch_news_en('Night Crows game when:14d')
    print('S4-NCGL ' + str(len(items)) + '개 수집')
    return items[:5]

def fetch_s4_fbjp():
    items = fetch_news('Baseball9 OR 파이널베이스볼 when:14d')
    if not items:
        items = fetch_news_en('Baseball9 mobile game when:14d')
    print('S4-FBJP ' + str(len(items)) + '개 수집')
    return items[:5]

def fetch_s4_wemade():
    items = fetch_news('Wemade OR 위메이드 OR WEMIX when:7d')
    print('S4-위메이드 ' + str(len(items)) + '개 수집')
    return items[:5]

def fetch_s5_marketing():
    ko = fetch_news('브랜드 캠페인 OR 숏폼 마케팅 OR UGC OR AI 마케팅 when:7d')
    en = fetch_news_en('brand campaign case OR UGC marketing OR AI marketing 2026 when:7d')
    items = _dedup(ko + en)[:5]
    print('S5-마케팅트렌드 ' + str(len(items)) + '개 수집')
    return items

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
                if name and name not in seen and 1 <= rank <= 10:
                    seen.add(name)
                    items.append({'rank': rank, 'name': name, 'link': link, 'pct': pct})
        items.sort(key=lambda x: x['rank'])
        print('게임트릭스 순위 ' + str(len(items)) + '개 수집')
        return items[:10]
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

    sources = load_sources()
    src_sections = sources.get('sections', {}) if sources else {}

    print('뉴스/AI/IT 병렬 수집 중...')
    tasks = {
        'news_wemade':        lambda: fetch_news('위메이드 OR 위믹스 OR WEMIX OR 레전드오브이미르 OR 나이트크로우'),
        'news_blockchain':    lambda: fetch_news('블록체인 OR 가상자산 OR NFT OR Web3 OR 코인 OR 스테이블코인'),
        'news_aiit':          lambda: fetch_news('ChatGPT OR Gemini OR 인공지능 OR AI 서비스 OR LLM OR IT 트렌드 when:3d'),
        'clipping':           lambda: fetch_marketing_news(),
        'marketing':          lambda: fetch_brand_insight_ko(),
        'brand_global':       lambda: fetch_brand_insight_global(),
        's3_ai':              lambda: fetch_s3_ai(),
        's3_game':            lambda: fetch_s3_game(),
        's3_wemade':          lambda: fetch_s3_wemade(),
        's3_blockchain':      lambda: fetch_s3_blockchain(),
        'gametrics':          lambda: fetch_gametrics_top(),
        'gplay_kr':           lambda: fetch_gplay_top('kr', 'ko', 'TOP_GROSSING'),
        'appstore_kr':        lambda: fetch_appstore_top('kr'),
        'stock_112040':       lambda: fetch_stock('112040'),
        'stock_101730':       lambda: fetch_stock('101730'),
        'wemix':              lambda: fetch_wemix(),
    }

    # Dashboard sections: driven by sources.json when available
    if src_sections:
        for sec_id, sec_cfg in src_sections.items():
            if not sec_cfg.get('enabled', True):
                continue
            queries = sec_cfg.get('queries', [])
            tasks['sec_' + sec_id] = (lambda sid=sec_id, qs=queries: fetch_section_generic(sid, qs))
    else:
        tasks.update({
            'sec_s1':        lambda: fetch_s1_game_trend(),
            'sec_s2':        lambda: fetch_s2_consumer(),
            'sec_s3':        lambda: fetch_s3_nextgen(),
            'sec_s4_lygl':   lambda: fetch_s4_lygl(),
            'sec_s4_ncgl':   lambda: fetch_s4_ncgl(),
            'sec_s4_fbjp':   lambda: fetch_s4_fbjp(),
            'sec_s4_wemade': lambda: fetch_s4_wemade(),
            'sec_s5':        lambda: fetch_s5_marketing(),
        })

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
        'aiit':         results.get('news_aiit', []),
        'clipping':     results.get('clipping', []),
        'marketing':    results.get('marketing', []),
        'brand_global': results.get('brand_global', []),
        's3_ai':        results.get('s3_ai', []),
        's3_game':      results.get('s3_game', []),
        's3_wemade':    results.get('s3_wemade', []),
        's3_blockchain':results.get('s3_blockchain', []),
    }
    rankings = {
        'gametrics':   results.get('gametrics', []),
        'gplay_kr':    results.get('gplay_kr', []),
        'appstore_kr': results.get('appstore_kr', []),
    }

    stocks = {
        'wemade':     results.get('stock_112040', {'err': '로드 실패'}),
        'wemade_max': results.get('stock_101730', {'err': '로드 실패'}),
        'wemix':      results.get('wemix', {'err': '로드 실패'}),
    }

    # Build flat s4_* sub-map from results
    s4_map = {}
    for key, val in results.items():
        if key.startswith('sec_s4_'):
            sub = key[len('sec_s4_'):]
            s4_map[sub] = val

    sections = {
        's1': results.get('sec_s1', []),
        's2': results.get('sec_s2', []),
        's3': results.get('sec_s3', []),
        's4': s4_map,
        's5': results.get('sec_s5', []),
    }

    # Write pending_articles.json (flat keys, 1-2 articles per section)
    pending = {}
    for key, items in results.items():
        if key.startswith('sec_'):
            sec_id = key[4:]  # strip 'sec_'
            pending[sec_id] = items[:2]
            if not items:
                print('WARNING: ' + sec_id + ' pending 0건 — 뉴스레터 콘텐츠 생성 불가')
    with open(PENDING_FILE, 'w', encoding='utf-8') as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)
    print('pending_articles.json 저장 (' + str(len(pending)) + '개 섹션)')

    data = {
        'updated': now,
        'news': news,
        'rankings': rankings,
        'stocks': stocks,
        'sections': sections,
    }

    with open(os.path.join(_BASE, 'data.json'), 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print('완료!')
    print('  뉴스-클리핑: ' + str(len(news['clipping'])) + '개')
    print('  뉴스-AI/IT: ' + str(len(news['aiit'])) + '개')
    print('  게임트릭스: ' + str(len(rankings['gametrics'])) + '개')
    print('  Google Play KR: ' + str(len(rankings['gplay_kr'])) + '개')
    print('  App Store KR: ' + str(len(rankings['appstore_kr'])) + '개')
    print('  위메이드 주가: ' + str(stocks['wemade']))
    print('  위메이드맥스 주가: ' + str(stocks['wemade_max']))
    print('  WEMIX: ' + str(stocks['wemix']))
    print('  S1: ' + str(len(sections['s1'])) + '개')
    print('  S2: ' + str(len(sections['s2'])) + '개')
    print('  S3: ' + str(len(sections['s3'])) + '개')
    for sub, items in sorted(sections['s4'].items()):
        print('  S4-' + sub + ': ' + str(len(items)) + '개')
    print('  S5: ' + str(len(sections['s5'])) + '개')

if __name__ == '__main__':
    main()
