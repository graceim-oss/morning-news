import json
import os
from datetime import datetime, timezone, timedelta

from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from apscheduler.schedulers.background import BackgroundScheduler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HISTORY_FILE = os.path.join(BASE_DIR, 'history.json')
ARTICLES_DIR = os.path.join(BASE_DIR, 'articles')
ARTICLES_FILE = os.path.join(ARTICLES_DIR, 'index.json')
KST = timezone(timedelta(hours=9))

app = Flask(__name__)
app.secret_key = 'wemade-newsletter-2026'

scheduler = BackgroundScheduler(timezone='Asia/Seoul')


# ── config helpers ────────────────────────────────────────────────────────────

def load_config():
    with open(os.path.join(BASE_DIR, 'config.json'), encoding='utf-8') as f:
        return json.load(f)


def save_config(cfg):
    with open(os.path.join(BASE_DIR, 'config.json'), 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ── history helpers ───────────────────────────────────────────────────────────

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    with open(HISTORY_FILE, encoding='utf-8') as f:
        return json.load(f)


def save_history(history):
    with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


# ── articles helpers ──────────────────────────────────────────────────────────

def load_articles():
    if not os.path.exists(ARTICLES_FILE):
        return {'articles': [], 'last_updated': ''}
    with open(ARTICLES_FILE, encoding='utf-8') as f:
        return json.load(f)


def save_articles(data):
    os.makedirs(ARTICLES_DIR, exist_ok=True)
    data['last_updated'] = datetime.now(KST).strftime('%Y-%m-%d %H:%M')
    with open(ARTICLES_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_history(result, is_test=False):
    history = load_history()
    history.insert(0, {
        'date': datetime.now(KST).strftime('%Y-%m-%d %H:%M'),
        'recipients': result.get('total', 0),
        'success': result.get('success', 0),
        'fail': result.get('fail', 0),
        'is_test': is_test,
    })
    save_history(history[:50])


# ── scheduler ────────────────────────────────────────────────────────────────

DAY_ABBR = {
    'monday': 'mon', 'tuesday': 'tue', 'wednesday': 'wed',
    'thursday': 'thu', 'friday': 'fri', 'saturday': 'sat', 'sunday': 'sun',
}


def scheduled_send():
    with app.app_context():
        try:
            from newsletter import build_newsletter_data, send_newsletter
            data = build_newsletter_data()
            html = render_template('email.html', **data)
            result = send_newsletter(html)
            add_history(result)
            print(f"[스케줄] 발송 완료: 성공 {result['success']}명")
        except Exception as e:
            print(f'[스케줄] 발송 오류: {e}')


def setup_scheduler():
    for job in scheduler.get_jobs():
        job.remove()
    cfg = load_config()
    sched = cfg.get('schedule', {})
    day = DAY_ABBR.get(sched.get('day', 'monday'), 'mon')
    scheduler.add_job(
        scheduled_send,
        'cron',
        day_of_week=day,
        hour=sched.get('hour', 9),
        minute=sched.get('minute', 0),
        id='newsletter_job',
        replace_existing=True,
    )


# ── next send time ────────────────────────────────────────────────────────────

def get_next_send(sched):
    day_map = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6,
    }
    now = datetime.now(KST)
    target = day_map.get(sched.get('day', 'monday'), 0)
    hour = sched.get('hour', 9)
    minute = sched.get('minute', 0)
    days_ahead = target - now.weekday()
    if days_ahead < 0 or (days_ahead == 0 and (now.hour > hour or (now.hour == hour and now.minute >= minute))):
        days_ahead += 7
    from datetime import timedelta as td
    nxt = (now + td(days=days_ahead)).replace(hour=hour, minute=minute, second=0, microsecond=0)
    day_names = ['월', '화', '수', '목', '금', '토', '일']
    return f"{nxt.strftime('%Y-%m-%d')} ({day_names[nxt.weekday()]}) {nxt.strftime('%H:%M')}"


# ── routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    cfg = load_config()
    history = load_history()
    return render_template('admin.html',
        page='home',
        cfg=cfg,
        history=history[:10],
        next_send=get_next_send(cfg.get('schedule', {})),
    )


@app.route('/recipients', methods=['GET', 'POST'])
def recipients():
    cfg = load_config()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            if email:
                cfg['recipients'].append({'name': name, 'email': email})
                save_config(cfg)
                flash(f'{email} 수신자가 추가되었습니다.', 'success')
            else:
                flash('이메일 주소를 입력해주세요.', 'error')
        elif action == 'delete':
            idx = int(request.form.get('index', -1))
            if 0 <= idx < len(cfg['recipients']):
                removed = cfg['recipients'].pop(idx)
                save_config(cfg)
                name = removed.get('email', '') if isinstance(removed, dict) else removed
                flash(f'{name} 수신자가 삭제되었습니다.', 'success')
        return redirect(url_for('recipients'))
    return render_template('admin.html', page='recipients', cfg=cfg)


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    cfg = load_config()
    if request.method == 'POST':
        cfg['gmail_user'] = request.form.get('gmail_user', '').strip()
        cfg['gmail_password'] = request.form.get('gmail_password', '').strip()
        cfg['gemini_api_key'] = request.form.get('gemini_api_key', '').strip()
        cfg['schedule']['day'] = request.form.get('day', 'monday')
        cfg['schedule']['hour'] = int(request.form.get('hour', 9))
        cfg['schedule']['minute'] = int(request.form.get('minute', 0))
        save_config(cfg)
        setup_scheduler()
        flash('설정이 저장되었습니다.', 'success')
        return redirect(url_for('settings'))
    return render_template('admin.html', page='settings', cfg=cfg)


@app.route('/content', methods=['GET', 'POST'])
def content():
    cfg = load_config()
    if request.method == 'POST':
        cfg['editor_comment'] = request.form.get('editor_comment', '').strip()
        if 'manual_notes' not in cfg:
            cfg['manual_notes'] = {}
        cfg['manual_notes']['section2'] = request.form.get('note_section2', '').strip()
        cfg['manual_notes']['section3'] = request.form.get('note_section3', '').strip()
        save_config(cfg)
        flash('콘텐츠가 저장되었습니다.', 'success')
        return redirect(url_for('content'))
    return render_template('admin.html', page='content', cfg=cfg)


@app.route('/preview')
def preview():
    try:
        from newsletter import build_newsletter_data
        data = build_newsletter_data()
        return render_template('email.html', **data)
    except Exception as e:
        return f'<pre style="padding:20px;color:red;">미리보기 오류:\n{e}</pre>'


@app.route('/send', methods=['POST'])
def send_all():
    try:
        from newsletter import build_newsletter_data, send_newsletter
        data = build_newsletter_data()
        html = render_template('email.html', **data)
        result = send_newsletter(html)
        add_history(result)
        flash(f"발송 완료: 성공 {result['success']}명 / 실패 {result['fail']}명", 'success')
    except Exception as e:
        flash(f'발송 오류: {e}', 'error')
    return redirect(url_for('index'))


@app.route('/test-send', methods=['POST'])
def test_send():
    cfg = load_config()
    gmail_user = cfg.get('gmail_user', '')
    if not gmail_user:
        flash('Gmail 계정을 먼저 설정에서 입력해주세요.', 'error')
        return redirect(url_for('index'))
    try:
        from newsletter import build_newsletter_data, send_newsletter
        data = build_newsletter_data()
        html = render_template('email.html', **data)
        result = send_newsletter(html, test_email=gmail_user)
        add_history(result, is_test=True)
        flash(f'테스트 발송 완료 → {gmail_user}', 'success')
    except Exception as e:
        flash(f'테스트 발송 오류: {e}', 'error')
    return redirect(url_for('index'))


# ── articles ──────────────────────────────────────────────────────────────────

@app.route('/articles')
def articles_page():
    data = load_articles()
    cats = ['브랜드인사이트', 'AI·IT', '트렌드', '캠페인사례']
    cat_filter = request.args.get('cat', '')
    arts = data['articles']
    if cat_filter:
        arts = [a for a in arts if a.get('category') == cat_filter]
    return render_template('admin.html',
        page='articles',
        articles=arts,
        all_articles=data['articles'],
        cats=cats,
        cat_filter=cat_filter,
    )


@app.route('/articles/crawl', methods=['POST'])
def articles_crawl():
    url = (request.json or {}).get('url', '').strip()
    if not url:
        return jsonify({'error': 'URL이 필요합니다.'}), 400
    try:
        from crawler import crawl_article
        result = crawl_article(url)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/articles/save', methods=['POST'])
def articles_save():
    raw = request.form.get('article_data', '')
    if not raw:
        flash('아티클 데이터가 없습니다.', 'error')
        return redirect(url_for('articles_page'))
    try:
        article = json.loads(raw)
    except Exception:
        flash('아티클 데이터 파싱 오류.', 'error')
        return redirect(url_for('articles_page'))
    article['category'] = request.form.get('category', '브랜드인사이트')
    data = load_articles()
    # prevent duplicate URL
    existing = [a for a in data['articles'] if a.get('url') == article.get('url')]
    if existing:
        flash('이미 등록된 URL입니다.', 'error')
        return redirect(url_for('articles_page'))
    data['articles'].insert(0, article)
    save_articles(data)
    flash(f'"{article.get("title", "아티클")[:40]}" 저장 완료', 'success')
    return redirect(url_for('articles_page'))


@app.route('/articles/delete', methods=['POST'])
def articles_delete():
    art_id = request.form.get('article_id', '')
    data = load_articles()
    before = len(data['articles'])
    data['articles'] = [a for a in data['articles'] if a.get('id') != art_id]
    if len(data['articles']) < before:
        save_articles(data)
        flash('아티클이 삭제되었습니다.', 'success')
    return redirect(url_for('articles_page'))


@app.route('/archive')
def archive():
    history = load_history()
    return render_template('admin.html', page='archive', history=history)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5001)
    args = parser.parse_args()

    setup_scheduler()
    scheduler.start()
    print(f'\n✅ 뉴스레터 관리자 서버 시작')
    print(f'📌 http://localhost:{args.port} 에서 확인하세요\n')
    app.run(debug=True, use_reloader=False, host='0.0.0.0', port=args.port)
