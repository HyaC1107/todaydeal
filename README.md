# 오늘딜

매일 아침 9시, 쿠팡 골드박스와 요일별 카테고리 베스트를 자동으로 모아 올리는 정적 사이트.
매일 가격을 저장해서 **어제보다 얼마나 내렸는지**, **30일 최저가인지**를 같이 보여준다.

- 데이터: 쿠팡 파트너스 Open API (`goldbox`, `bestcategories`) — 하루 호출 2회
- 생성: Python + Jinja2 → `site/` → GitHub Pages
- 스케줄: GitHub Actions cron (00:00 UTC = 09:00 KST)
- 요일: 월 식품 · 화 주방 · 수 가전디지털 · 목 생활용품 · 금 뷰티 · 토 스포츠레저 · 일 반려동물

```
src/coupang_deals/coupang_api.py   HMAC 인증 클라이언트
src/coupang_deals/collect.py       수집 → data/snapshots/YYYY-MM-DD.json + data/prices.json
src/coupang_deals/render.py        data/ → site/
templates/                         base · index · post · _card · style.css
scripts/daily.py                   collect + render
```

로컬 실행: `.env.example` → `.env` 채우고 `uv run python scripts/daily.py`

모든 페이지에 파트너스 고지문이 들어간다. 사이트명·도메인에 "쿠팡"을 쓰지 않는다(파트너스 정책).
