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

def main():
    now = datetime.now(KST).strftime('%H:%M:%S')
    print(f'수집 시작: {now}')
    data = {
        'updated': now,
        'stocks': {
            'wemade':     fetch_stock('112040'),
            'wemade_max': fetch_stock('101730'),
            'wemix':      fetch_wemix(),
        },
        'news': {
            'wemade':     fetch_news('위메이드 OR 위믹스 OR WEMIX'),
            'blockchain': fetch_news('블록체인 OR 가상자산 OR NFT OR Web3'),
            'marketing':  fetch_news('브랜딩 OR 마케팅트렌드 OR 디지털마케팅'),
        },
        'trends': {
            'kr':     fetch_gtrend('KR'),
            'global': fetch_gtrend('US'),
        },
    }
    with open('data.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print('완료! data.json 저장됨')

if __name__ == '__main__':
    main()
