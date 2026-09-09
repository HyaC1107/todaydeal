"""매일 1회 수집 — 골드박스 + 요일별 카테고리 베스트 → data/snapshots/YYYY-MM-DD.json + 가격 이력.

API 호출은 하루 2회로 고정한다(골드박스 1, 카테고리 1). 파트너스 API 호출 한도가 빡빡하다.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .coupang_api import CATEGORIES, CoupangPartners

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SNAPSHOTS = DATA / "snapshots"
PRICES = DATA / "prices.json"

#: 요일(월=0) → 카테고리명. PM 지정: 월 식품·수 가전·금 뷰티, 나머지는 클또리 임시 배정.
WEEKDAY_CATEGORY: dict[int, str] = {
    0: "식품", 1: "주방용품", 2: "가전디지털", 3: "생활용품", 4: "뷰티", 5: "스포츠레저", 6: "반려동물용품",
}
WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]
HISTORY_DAYS = 120


def _slim(it: dict[str, Any]) -> dict[str, Any]:
    """API 응답에서 쓰는 필드만. 가격은 정수 원."""
    return {
        "id": str(it.get("productId")),
        "name": str(it.get("productName", "")).strip(),
        "price": int(float(it.get("productPrice") or 0)),
        "image": it.get("productImage"),
        "url": it.get("productUrl"),
        "rocket": bool(it.get("isRocket")),
        "free_shipping": bool(it.get("isFreeShipping")),
        "rank": int(it.get("rank") or 0),
        "category": it.get("categoryName"),
    }


def _load_prices() -> dict[str, Any]:
    if PRICES.exists():
        return json.loads(PRICES.read_text(encoding="utf-8"))
    return {}


def _update_prices(prices: dict[str, Any], items: list[dict[str, Any]], today: str) -> None:
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
    for it in items:
        rec = prices.setdefault(it["id"], {"name": it["name"], "history": []})
        rec["name"] = it["name"]
        hist = [h for h in rec["history"] if h[0] != today and h[0] >= cutoff]
        hist.append([today, it["price"]])
        rec["history"] = sorted(hist)


def collect(now: datetime | None = None) -> Path:
    now = now or datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    wd = now.weekday()
    cat_name = WEEKDAY_CATEGORY[wd]
    cat_id = CATEGORIES[cat_name]

    api = CoupangPartners()
    try:
        goldbox = [_slim(x) for x in api.goldbox(sub_id="goldbox")]
        best = [_slim(x) for x in api.best_category(cat_id, limit=10, sub_id="best")]
    finally:
        api.close()

    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    snap = {
        "date": today,
        "weekday": WEEKDAY_KO[wd],
        "collected_at": now.strftime("%Y-%m-%d %H:%M"),
        "category": cat_name,
        "category_id": cat_id,
        "goldbox": goldbox,
        "best": best,
    }
    out = SNAPSHOTS / f"{today}.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")

    prices = _load_prices()
    _update_prices(prices, goldbox + best, today)
    PRICES.write_text(json.dumps(prices, ensure_ascii=False), encoding="utf-8")
    return out


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    p = collect()
    d = json.loads(p.read_text(encoding="utf-8"))
    print(f"saved {p.name}: goldbox {len(d['goldbox'])} · {d['category']} best {len(d['best'])}")
