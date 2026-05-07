import json
import os
import smtplib
import ssl
from datetime import datetime, timezone, timedelta
from urllib.request import urlopen, Request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DATA = os.path.join(os.path.dirname(BASE_DIR), 'data.json')  # morning-news/data.json
DATA_URL = "https://raw.githubusercontent.com/graceim-oss/morning-news/main/data.json"
DASHBOARD_URL = "https://graceim-oss.github.io/morning-news/"
KST = timezone(timedelta(hours=9))


def load_config():
    with open(os.path.join(BASE_DIR, 'config.json'), encoding='utf-8') as f:
        return json.load(f)


def save_config(cfg):
    with open(os.path.join(BASE_DIR, 'config.json'), 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def fetch_remote_data():
    # 로컬 data.json 우선 (fetch_data.py 실행 결과), 없으면 원격 GitHub
    if os.path.exists(LOCAL_DATA):
        try:
            with open(LOCAL_DATA, encoding='utf-8') as f:
                data = json.load(f)
            print(f'로컬 data.json 로드 완료 (업데이트: {data.get("updated", "?")})')
            return data
        except Exception as e:
            print(f'로컬 데이터 로드 실패, 원격으로 시도: {e}')
    req = Request(DATA_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urlopen(req, timeout=20) as r:
        print('원격 data.json 로드 완료')
        return json.loads(r.read().decode('utf-8'))


def gemini_comment(api_key, prompt):
    try:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        for model_name in ('gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-flash-latest', 'gemini-2.0-flash-lite'):
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                text = response.text.strip()
                if text:
                    print(f'Gemini OK ({model_name}): {text[:40]}…')
                    return text
            except Exception as e:
                print(f'Gemini 모델 실패 ({model_name}): {e}')
                continue
        print('Gemini: 사용 가능한 모델 없음, fallback으로 빈 코멘트 반환')
        return ''
    except Exception as e:
        print(f'Gemini 초기화 오류: {e}')
        return ''


def build_section1(data, api_key, note=''):
    insights = data.get('insights', [])[:3]

    # Fallback to marketing news if insights are empty
    if not insights:
        news = data.get('news', {})
        marketing = news.get('marketing', [])[:2]
        brand_global = news.get('brand_global', [])[:1]
        for a in (marketing + brand_global)[:3]:
            insights.append({
                'title': a.get('title', ''),
                'link': a.get('link', ''),
                'source': a.get('source', 'Google News'),
                'published': a.get('published', ''),
                'image': '',
                'description': '',
                'tags': [],
            })

    items = []
    for insight in insights:
        title = insight.get('title', '')
        source = insight.get('source', 'Google News')
        description = insight.get('description', '')
        tags = insight.get('tags', [])
        comment = ''
        if api_key and title:
            tags_str = ', '.join(tags) if tags else ''
            prompt = f"""당신은 위메이드 브랜드마케팅팀 소속 시니어 마케터입니다.
아래 아티클을 읽고 마케띵킹/큐레터 스타일의 인사이트 코멘트를 작성해주세요.

작성 규칙:
- 블로그 아티클처럼 자연스럽고 읽기 좋은 문체
- 단순 요약 금지 — '왜 우리가 주목해야 하는가', '어떻게 활용할 수 있는가' 중심
- 위메이드/게임 IP/크리에이터 마케팅 관점 연결 필수
- 소제목 없이 연속적인 단락으로
- 400~500자 내외
- 이모지 2~3개 자연스럽게 포함
- 마지막 문장은 실무 활용 힌트로 마무리

아티클 제목: {title}
출처: {source}
요약: {description}
키워드: {tags_str}"""
            comment = gemini_comment(api_key, prompt)
        items.append({
            'title': title,
            'link': insight.get('link', ''),
            'source': source,
            'published': insight.get('published', ''),
            'image': insight.get('image', ''),
            'description': description,
            'tags': tags,
            'comment': comment,
        })
    return {'articles': items, 'note': note}


def build_section2(data, api_key, note=''):
    trends = data.get('trends', {})
    trend_kr = trends.get('kr', [])[:5]
    rankings = data.get('rankings', {})
    gametrics = rankings.get('gametrics', [])[:3]
    gplay_kr = rankings.get('gplay_kr', [])[:3]

    keywords = [t.get('title', '') for t in trend_kr if t.get('title')]
    top_game = gametrics[0].get('name', '정보 없음') if gametrics else '정보 없음'

    comment = ''
    if api_key and keywords:
        prompt = f"""당신은 위메이드 브랜드마케팅팀 소속 트렌드 분석가입니다.
이번 주 한국 실시간 검색어 TOP5: {', '.join(keywords)}
게임 순위 1위: {top_game}

큐레터/마케띵킹 스타일로 브랜드 마케터 관점 트렌드 해석을 작성해주세요.

스타일 규칙:
- '요즘 사람들은 ~에 빠져있어요' 식의 트렌드 읽기
- 연령대/세대 관점 포함하면 좋음
- 게임 마케팅과 연결 가능한 포인트 1개 포함
- 3~4문장, 친근한 구어체
- 이모지 자연스럽게 포함"""
        comment = gemini_comment(api_key, prompt)

    return {
        'trend_kr': trend_kr,
        'gametrics': gametrics,
        'gplay_kr': gplay_kr,
        'comment': comment,
        'note': note,
    }


def build_section3(data, api_key, note=''):
    aiit = data.get('news', {}).get('aiit', [])[:5]
    titles = [a.get('title', '') for a in aiit if a.get('title')][:3]

    comment = ''
    if api_key and titles:
        prompt = f"""당신은 디지털 마케팅에 관심 많은 브랜드 마케터입니다.
이번 주 AI/IT 뉴스 TOP3 제목: {', '.join(titles)}

Trend A Word 스타일로 브랜드 마케터가 꼭 알아야 할 핵심을 작성해주세요.

스타일 규칙:
- '이번 주 꼭 알아야 할 IT 키워드는 ~입니다' 형식으로 시작
- 마케팅 업무에 직접 연결되는 활용 포인트 포함
- 너무 기술적이지 않게, 실무자 눈높이로
- 3~4문장, 간결하고 임팩트 있게
- 이모지 포함"""
        comment = gemini_comment(api_key, prompt)

    return {'articles': aiit, 'comment': comment, 'note': note}


def _fmt_stock(s):
    if not s or s.get('err'):
        return {'error': True}
    return {
        'error': False,
        'price': s.get('price', '-'),
        'change': s.get('change', '0'),
        'ratio': s.get('ratio', '0'),
        'dir': s.get('dir', 'STEADY').lower(),
        'sign': s.get('sign', ''),
    }


def _fmt_wemix(w):
    if not w or w.get('err'):
        return {'error': True}
    krw = w.get('krw', 0)
    chg = w.get('chg24h', 0)
    return {
        'error': False,
        'krw': '{:,.0f}'.format(krw),
        'chg': '{:.1f}'.format(abs(chg)),
        'dir': w.get('dir', 'STEADY').lower(),
        'sign': w.get('sign', ''),
    }


def build_newsletter_data():
    cfg = load_config()
    api_key = cfg.get('gemini_api_key', '')
    notes = cfg.get('manual_notes', {})

    try:
        data = fetch_remote_data()
    except Exception as e:
        print(f'원격 데이터 로드 오류: {e}')
        data = {}

    raw_stocks = data.get('stocks', {})
    stocks = {
        'wemade': _fmt_stock(raw_stocks.get('wemade', {})),
        'wemade_max': _fmt_stock(raw_stocks.get('wemade_max', {})),
        'wemix': _fmt_wemix(raw_stocks.get('wemix', {})),
    }

    now = datetime.now(KST)
    return {
        'date': now.strftime('%Y년 %m월 %d일'),
        'year': now.year,
        'section1': build_section1(data, api_key, notes.get('section1', '')),
        'section2': build_section2(data, api_key, notes.get('section2', '')),
        'section3': build_section3(data, api_key, notes.get('section3', '')),
        'stocks': stocks,
        'editor_comment': cfg.get('editor_comment', ''),
        'dashboard_url': DASHBOARD_URL,
    }


def send_newsletter(html_content, recipients=None, test_email=None):
    cfg = load_config()
    gmail_user = cfg.get('gmail_user', '')
    gmail_password = cfg.get('gmail_password', '')

    if not gmail_user or not gmail_password:
        raise ValueError('Gmail 계정 설정이 없습니다. 발송 설정을 먼저 완료해주세요.')

    if test_email:
        target_emails = [test_email]
    elif recipients is not None:
        target_emails = recipients
    else:
        raw = cfg.get('recipients', [])
        target_emails = [r['email'] if isinstance(r, dict) else r for r in raw]

    target_emails = [e for e in target_emails if e]
    if not target_emails:
        raise ValueError('수신자가 없습니다. 수신자 목록을 먼저 추가해주세요.')

    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText

    now = datetime.now(KST)
    subject = f"[위메이드 브랜드마케팅팀] 위클리 뉴스레터 {now.strftime('%Y년 %m월 %d일')}"

    success, fail = 0, 0
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ctx) as server:
        server.login(gmail_user, gmail_password)
        for email in target_emails:
            try:
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = gmail_user
                msg['To'] = email
                msg.attach(MIMEText(html_content, 'html', 'utf-8'))
                server.sendmail(gmail_user, email, msg.as_string())
                success += 1
            except Exception as e:
                print(f'발송 실패 ({email}): {e}')
                fail += 1

    return {'success': success, 'fail': fail, 'total': len(target_emails)}
