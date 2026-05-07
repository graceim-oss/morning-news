import re, uuid
import requests
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse
from bs4 import BeautifulSoup

KST = timezone(timedelta(hours=9))

_NOISE_TAGS = ['script', 'style', 'nav', 'footer', 'header', 'aside',
               'iframe', 'noscript', 'form', 'button']
_NOISE_CLASS = re.compile(
    r'\b(ad|ads|advertisement|nav|navigation|footer|sidebar|menu|banner|'
    r'popup|modal|share|social|comment|related|recommend|widget|cookie)\b', re.I)
_NOISE_ID = re.compile(
    r'\b(ad|ads|nav|footer|sidebar|menu|banner|popup|modal|share|comment|related)\b', re.I)
_CONTENT_CSS = [
    'article', '.article-content', '.post-content', '.entry-content',
    '.article-body', '.content-body', '.post-body', '.news-content',
    '.view-content', '.news_view', '.article_view',
    'main', '[role="main"]', '#content', '#article', '#main',
    '.content', '.post', '.article',
]

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                  'AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
}


def crawl_article(url):
    result = {
        'id': str(uuid.uuid4()),
        'url': url,
        'title': '',
        'source': _domain(url),
        'full_text': '',
        'image': '',
        'published': '',
        'category': '브랜드인사이트',
        'added_at': datetime.now(KST).strftime('%Y-%m-%d %H:%M'),
        'used_count': 0,
        'last_used': '',
        'success': False,
    }

    try:
        r = requests.get(url, headers=HEADERS, timeout=15, verify=False)
        r.raise_for_status()
        enc = r.apparent_encoding or 'utf-8'
        html_text = r.content.decode(enc, errors='replace')
        try:
            soup = BeautifulSoup(html_text, 'lxml')
        except Exception:
            soup = BeautifulSoup(html_text, 'html.parser')

        result['title'] = _og(soup, 'title') or _page_title(soup)
        result['image'] = _og(soup, 'image')
        og_desc = _og(soup, 'description')

        # strip noise
        for tag in soup.find_all(_NOISE_TAGS):
            tag.decompose()
        for tag in soup.find_all(class_=_NOISE_CLASS):
            tag.decompose()
        for tag in soup.find_all(id=_NOISE_ID):
            tag.decompose()

        body = _find_main(soup)
        raw = body.get_text(separator='\n', strip=True)
        text = _clean(raw)

        if len(text) < 150 and og_desc:
            text = og_desc

        result['full_text'] = text[:5000]
        result['success'] = True

    except Exception as e:
        result['error'] = str(e)
        result['full_text'] = ''

    return result


def _domain(url):
    try:
        return urlparse(url).netloc.replace('www.', '')
    except Exception:
        return url[:50]


def _og(soup, prop):
    tag = (soup.find('meta', property=f'og:{prop}') or
           soup.find('meta', attrs={'name': f'og:{prop}'}))
    return (tag.get('content') or '').strip() if tag else ''


def _page_title(soup):
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find('h1')
    return h1.get_text(strip=True) if h1 else ''


def _find_main(soup):
    for sel in _CONTENT_CSS:
        try:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 200:
                return el
        except Exception:
            continue
    return soup.find('body') or soup


def _clean(text):
    text = re.sub(r'[ \t]{2,}', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
