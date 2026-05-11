import json, os, re, subprocess, sys

_BASE = os.path.dirname(os.path.abspath(__file__))
PENDING_FILE = os.path.join(_BASE, 'pending_articles.json')
DATA_FILE    = os.path.join(_BASE, 'data.json')
SOURCES_FILE = os.path.join(_BASE, 'newsletter-admin', 'sources.json')

PROMPT_TMPL = """\
다음은 "{label}" 섹션의 최신 뉴스 기사 요약이야.
{articles}

위 기사를 바탕으로 위메이드 브랜드마케팅팀 주간 뉴스레터용 인사이트를 작성해줘.
반드시 아래 JSON 형식만 출력해. 설명이나 코드블록 없이 JSON만.

{{
  "headline": "한 줄 핵심 제목 (30자 이내)",
  "body": "2-3문장 인사이트 요약. 팀에 실질적으로 유용한 시사점 중심.",
  "point": "마케팅팀 액션 포인트 (1문장)"
}}"""


def _parse_claude_json(text):
    # Try fenced code block first
    m = re.search(r'```(?:json)?\s*(\{[\s\S]*?\})\s*```', text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # Walk backward from last '{' — handles nested braces correctly
    pos = len(text)
    while True:
        start = text.rfind('{', 0, pos)
        if start < 0:
            break
        try:
            obj = json.loads(text[start:])
            if 'headline' in obj:
                return obj
        except Exception:
            pass
        pos = start
    return None


def load_sources():
    try:
        with open(SOURCES_FILE, encoding='utf-8') as f:
            return json.load(f).get('sections', {})
    except Exception:
        return {}


def call_claude(prompt):
    try:
        result = subprocess.run(
            ['claude', '-p', prompt],
            capture_output=True, text=True, timeout=120,
            env={**os.environ},
        )
        if result.returncode != 0:
            print('WARNING: claude 비정상 종료 (code=' + str(result.returncode) + '): ' +
                  result.stderr[:300].strip())
            return ''
        return result.stdout.strip()
    except Exception as e:
        print('claude 호출 실패: ' + str(e))
        return ''


def main():
    if not os.path.exists(PENDING_FILE):
        print('ERROR: pending_articles.json 없음. fetch_data.py 먼저 실행하세요.')
        sys.exit(1)

    try:
        with open(PENDING_FILE, encoding='utf-8') as f:
            pending = json.load(f)
    except json.JSONDecodeError as e:
        print('ERROR: pending_articles.json 파싱 실패 — ' + str(e))
        sys.exit(1)

    sections_meta = load_sources()

    # Load existing data.json
    data = {}
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, encoding='utf-8') as f:
            data = json.load(f)

    generated = {}
    sample_printed = False

    for sec_id, articles in pending.items():
        if not articles:
            print('SKIP ' + sec_id + ': 기사 없음')
            generated[sec_id] = None
            continue

        label = sections_meta.get(sec_id, {}).get('label', sec_id)
        articles_text = '\n'.join(
            str(i + 1) + '. ' + a.get('title', '') + ' — ' + a.get('description', '')[:120]
            for i, a in enumerate(articles)
        )
        prompt = PROMPT_TMPL.format(label=label, articles=articles_text)

        print('생성 중: ' + sec_id + ' (' + label + ')')
        raw = call_claude(prompt)
        parsed = _parse_claude_json(raw) if raw else None

        if parsed:
            generated[sec_id] = parsed
            if not sample_printed:
                print('\n[샘플 - ' + sec_id + ']')
                print('  헤드라인: ' + parsed.get('headline', ''))
                print('  본문: ' + parsed.get('body', ''))
                print('  포인트: ' + parsed.get('point', ''))
                print()
                sample_printed = True
        else:
            print('WARNING: ' + sec_id + ' JSON 파싱 실패 — null 저장')
            generated[sec_id] = None

    data['generated_content'] = generated
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    success = sum(1 for v in generated.values() if v)
    print('완료: ' + str(success) + '/' + str(len(generated)) + '개 섹션 생성')


if __name__ == '__main__':
    main()
