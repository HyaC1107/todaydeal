"""매일 1회 수집 — 골드박스 + 카테고리 7종 전부 → data/snapshots/YYYY-MM-DD.json + 가격·순위 이력.

API 호출은 하루 최대 8회(골드박스 1 + 카테고리 7) + 저녁 골드박스 재조회 1회. 카테고리 하나가 실패해도
나머지는 살린다 — 실패한 탭은 렌더 단계에서 가장 최근 성공분을 쓴다.

가격 이력 항목: [date, price, vendorItemId]. 같은 productId라도 옵션·판매자(vendorItemId)가 다르면
다른 가격이므로, 비교는 vendorItemId가 같은 관측끼리만 한다(2026-09-10 챗또리 자문 반영).
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .coupang_api import CATEGORIES, CoupangError, CoupangPartners

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SNAPSHOTS = DATA / "snapshots"
EVENING = DATA / "goldbox-evening"
PRICES = DATA / "prices.json"
RANKS = DATA / "ranks.json"

TABS: list[tuple[str, str, str]] = [
    ("식품", "food", "식품"),
    ("주방용품", "kitchen", "주방"),
    ("가전디지털", "digital", "가전"),
    ("생활용품", "living", "생활"),
    ("뷰티", "beauty", "뷰티"),
    ("스포츠레저", "sports", "스포츠"),
    ("반려동물용품", "pet", "반려"),
]
SLUG_OF = {name: slug for name, slug, _ in TABS}

WEEKDAY_CATEGORY: dict[int, str] = {
    0: "식품", 1: "주방용품", 2: "가전디지털", 3: "생활용품", 4: "뷰티", 5: "스포츠레저", 6: "반려동물용품",
}
WEEKDAY_KO = ["월", "화", "수", "목", "금", "토", "일"]
HISTORY_DAYS = 120
CALL_GAP_SEC = 1.5


def _vendor_item_id(url: str) -> str:
    m = re.search(r"vendorItemId=(\d+)", url or "")
    return m.group(1) if m else ""


def _slim(it: dict[str, Any]) -> dict[str, Any]:
    url = it.get("productUrl") or ""
    return {
        "id": str(it.get("productId")),
        "vid": _vendor_item_id(url),
        "name": str(it.get("productName", "")).strip(),
        "price": int(float(it.get("productPrice") or 0)),
        "image": it.get("productImage"),
        "url": url,
        "rocket": bool(it.get("isRocket")),
        "free_shipping": bool(it.get("isFreeShipping")),
        "rank": int(it.get("rank") or 0),
        "category": it.get("categoryName"),
    }


def _load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _update_prices(prices: dict[str, Any], items: list[dict[str, Any]], today: str) -> None:
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
    for it in items:
        rec = prices.setdefault(it["id"], {"name": it["name"], "history": []})
        rec["name"] = it["name"]
        hist = [h for h in rec["history"] if h[0] != today and h[0] >= cutoff]
        hist.append([today, it["price"], it.get("vid", "")])
        rec["history"] = sorted(hist)


def _update_ranks(ranks: dict[str, Any], cat: str, items: list[dict[str, Any]], today: str) -> None:
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=HISTORY_DAYS)).strftime("%Y-%m-%d")
    bucket = ranks.setdefault(cat, {})
    for it in items:
        hist = [h for h in bucket.get(it["id"], []) if h[0] != today and h[0] >= cutoff]
        hist.append([today, it["rank"]])
        bucket[it["id"]] = sorted(hist)


def collect(now: datetime | None = None) -> Path:
    now = now or datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    wd = now.weekday()
    featured = WEEKDAY_CATEGORY[wd]

    api = CoupangPartners()
    errors: dict[str, str] = {}
    categories: dict[str, list[dict[str, Any]]] = {}
    try:
        try:
            goldbox = [_slim(x) for x in api.goldbox(sub_id="goldbox")]
        except CoupangError as e:
            goldbox, errors["goldbox"] = [], str(e)[:200]
        for name, _slug, _label in TABS:
            time.sleep(CALL_GAP_SEC)
            try:
                categories[name] = [_slim(x) for x in api.best_category(CATEGORIES[name], limit=10, sub_id="best")]
            except CoupangError as e:
                errors[name] = str(e)[:200]
    finally:
        api.close()

    SNAPSHOTS.mkdir(parents=True, exist_ok=True)
    snap = {
        "date": today,
        "weekday": WEEKDAY_KO[wd],
        "collected_at": now.strftime("%Y-%m-%d %H:%M"),
        "category": featured,
        "category_id": CATEGORIES[featured],
        "goldbox": goldbox,
        "best": categories.get(featured, []),
        "categories": categories,
        "errors": errors,
    }
    out = SNAPSHOTS / f"{today}.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1), encoding="utf-8")

    prices = _load(PRICES)
    ranks = _load(RANKS)
    all_items = goldbox + [it for lst in categories.values() for it in lst]
    _update_prices(prices, all_items, today)
    for cat, lst in categories.items():
        _update_ranks(ranks, cat, lst, today)
    PRICES.write_text(json.dumps(prices, ensure_ascii=False), encoding="utf-8")
    RANKS.write_text(json.dumps(ranks, ensure_ascii=False), encoding="utf-8")
    return out


def refresh_goldbox(now: datetime | None = None) -> Path:
    """저녁 재조회(1회) — 아침 가격을 그대로 재전송하지 않기 위해. data/goldbox-evening/YYYY-MM-DD.json"""
    now = now or datetime.now(KST)
    today = now.strftime("%Y-%m-%d")
    api = CoupangPartners()
    try:
        items = [_slim(x) for x in api.goldbox(sub_id="goldbox")]
    finally:
        api.close()
    EVENING.mkdir(parents=True, exist_ok=True)
    out = EVENING / f"{today}.json"
    out.write_text(json.dumps({"date": today, "collected_at": now.strftime("%Y-%m-%d %H:%M"), "goldbox": items}, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    p = collect()
    d = json.loads(p.read_text(encoding="utf-8"))
    ok = ", ".join(f"{k} {len(v)}" for k, v in d["categories"].items())
    print(f"saved {p.name}: goldbox {len(d['goldbox'])} · {ok}")
    if d["errors"]:
        print("errors:", d["errors"])
