# morning-news — 위메이드 브랜드마케팅팀 뉴스레터 시스템

## 프로젝트 구조

```
morning-news/
├── fetch_data.py                    # 뉴스·주가·게임순위 병렬 수집 → data.json
├── data.json                        # GitHub Pages 대시보드용 정적 데이터
├── index.html                       # GitHub Pages 퍼블릭 대시보드
└── newsletter-admin/                # Flask 관리자 서버 (localhost:5001)
    ├── app.py                       # Flask 라우트 + /api/dashboard + /api/analyze
    ├── newsletter.py                # 뉴스레터 빌드 로직 (Claude AI 인사이트 생성)
    ├── crawler.py                   # 아티클 URL 크롤러
    ├── config.json                  # Gmail·수신자·스케줄 설정
    ├── source_rotation.json         # 브랜드 인사이트 소스 로테이션 상태
    └── templates/
        ├── admin.html               # 관리자 대시보드 UI (Bootstrap 5.3)
        └── email.html               # 발송용 이메일 템플릿
```

## 실행 방법

```bash
# 데이터 수집 (data.json 갱신)
python3 fetch_data.py

# 관리자 서버 실행
cd newsletter-admin && python3 app.py --port 5001
# → http://localhost:5001
```

## 주요 기술

- **수집**: Google News RSS, 네이버 주가 API, CoinGecko, Gametrics, Google Play, App Store
- **AI**: `claude -p` subprocess로 인사이트 생성 (Claude Code CLI 활용)
- **발송**: Gmail SMTP (앱 비밀번호)
- **스케줄**: APScheduler (매주 지정 요일·시간 자동 발송)
- **대시보드**: Bootstrap 5.3, /api/dashboard + /api/analyze 순차 로딩

## 데이터 흐름

```
fetch_data.py → data.json → /api/dashboard → admin.html (5섹션 탭)
                                           ↓
                               /api/analyze (Claude 시사점) → 카드별 AI 인사이트
newsletter.py → email.html → Gmail SMTP → 수신자
```

## gstack

Available skills: /office-hours, /plan-eng-review, /review, /qa, /ship, /cso, /careful, /freeze, /guard, /unfreeze, /investigate, /document-release
