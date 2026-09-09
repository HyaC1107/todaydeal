"""정적 사이트 생성 — data/ → site/.

페이지: index(오늘 요약) · posts/YYYY-MM-DD(일일 다이제스트) · c/<slug>(카테고리 탭, 매일 갱신) · goldbox
신호: 가격(어제보다·30일 최저가) + 순위(어제 대비 ▲▼·연속 TOP10일수). 전부 자체 이력에서 계산.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .collect import SLUG_OF, TABS

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SITE = ROOT / "site"
TEMPLATES = ROOT / "templates"
SITE_NAME = "오늘딜"
DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."


def _won(n: int) -> str:
    return f"{n:,}"


def _load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _price_signals(prices: dict[str, Any], pid: str, price: int, today: str) -> dict[str, Any]:
    out: dict[str, Any] = {"vs_yesterday": None, "low30": False, "days": 0}
    rec = prices.get(pid)
    if not rec:
        return out
    hist = [(d, p) for d, p in rec["history"] if d <= today]
    out["days"] = len(hist)
    if len(hist) < 2:
        return out
    prev_price = hist[-2][1]
    if prev_price and prev_price != price:
        out["vs_yesterday"] = round((price - prev_price) / prev_price * 100)
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    window = [p for d, p in hist if cutoff <= d < today]
    if window and price <= min(window):
        out["low30"] = True
    return out


def _rank_signals(ranks: dict[str, Any], cat: str, pid: str, rank: int, today: str) -> dict[str, Any]:
    """어제 대비 순위 변동(양수=상승), 연속 TOP10 일수, 신규 진입 여부."""
    out: dict[str, Any] = {"delta": None, "streak": 1, "new": False}
    hist = [(d, r) for d, r in ranks.get(cat, {}).get(pid, []) if d <= today]
    if len(hist) < 2:
        out["new"] = len(hist) == 1 and ranks.get(cat) is not None and any(
            len(v) >= 2 for v in ranks[cat].values()
        )  # 이력이 쌓인 카테고리에서 오늘 처음 보이면 신규
        return out
    prev_date, prev_rank = hist[-2]
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    if prev_date == yesterday:
        out["delta"] = prev_rank - rank
    # 연속 일수: 오늘부터 거꾸로 하루씩 붙어 있는 만큼
    streak, cur = 1, datetime.strptime(today, "%Y-%m-%d")
    dates = {d for d, _ in hist}
    while (cur - timedelta(days=1)).strftime("%Y-%m-%d") in dates:
        streak += 1
        cur -= timedelta(days=1)
    out["streak"] = streak
    return out


def _spark(prices: dict[str, Any], pid: str, today: str) -> list[tuple[str, int]]:
    rec = prices.get(pid)
    return [(d, p) for d, p in rec["history"] if d <= today][-30:] if rec else []


def _decorate(items: list[dict[str, Any]], prices: dict[str, Any], ranks: dict[str, Any], cat: str | None, today: str) -> None:
    for it in items:
        it["sig"] = _price_signals(prices, it["id"], it["price"], today)
        it["rk"] = _rank_signals(ranks, cat, it["id"], it["rank"], today) if cat else {"delta": None, "streak": 1, "new": False}


def _latest_for_category(snaps: list[dict[str, Any]], cat: str) -> tuple[str | None, list[dict[str, Any]]]:
    """해당 카테고리가 성공한 가장 최근 스냅샷(오늘 실패했으면 어제 것)."""
    for d in reversed(snaps):
        lst = d.get("categories", {}).get(cat) or (d.get("best") if d.get("category") == cat else None)
        if lst:
            return d["date"], lst
    return None, []


def render() -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    env.filters["won"] = _won
    prices = _load(DATA / "prices.json")
    ranks = _load(DATA / "ranks.json")
    snap_files = sorted((DATA / "snapshots").glob("*.json"))
    if not snap_files:
        raise SystemExit("data/snapshots 가 비어 있다 — collect 먼저")
    snaps = [json.loads(p.read_text(encoding="utf-8")) for p in snap_files]

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "posts").mkdir(parents=True)
    (SITE / "c").mkdir()
    shutil.copy(TEMPLATES / "style.css", SITE / "style.css")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")

    tabs = [{"name": n, "slug": s, "label": l} for n, s, l in TABS]
    common = {"site": SITE_NAME, "disclosure": DISCLOSURE, "tabs": tabs}

    # 일일 다이제스트
    posts: list[dict[str, Any]] = []
    for d in snaps:
        today = d["date"]
        _decorate(d["goldbox"], prices, ranks, None, today)
        _decorate(d["best"], prices, ranks, d["category"], today)
        if d["goldbox"]:
            d["goldbox"][0]["spark"] = _spark(prices, d["goldbox"][0]["id"], today)
        allitems = d["goldbox"] + d["best"]
        d["summary"] = {
            "drop": sum(1 for it in allitems if (it["sig"]["vs_yesterday"] or 0) < 0),
            "low": sum(1 for it in allitems if it["sig"]["low30"]),
        }
        d["title"] = f"{d['weekday']}요일 {d['category']} 베스트 10 + 골드박스 {len(d['goldbox'])}"
        d["slug"] = SLUG_OF.get(d["category"], "")
        posts.append(d)
    latest = posts[-1]
    today = latest["date"]

    tpl_post = env.get_template("post.html")
    for d in posts:
        (SITE / "posts" / f"{d['date']}.html").write_text(tpl_post.render(post=d, active="post", **common), encoding="utf-8")

    # 카테고리 탭 페이지 — 매일 갱신, 오늘 실패했으면 최근 성공분
    tpl_cat = env.get_template("category.html")
    cat_meta: list[dict[str, Any]] = []
    for n, s, l in TABS:
        date, items = _latest_for_category(snaps, n)
        items = [dict(x) for x in items]
        _decorate(items, prices, ranks, n, date or today)
        if items:
            items[0]["spark"] = _spark(prices, items[0]["id"], date or today)
        stale = bool(date and date != today)
        cat_meta.append({"name": n, "slug": s, "label": l, "date": date, "count": len(items), "stale": stale, "top": items[0] if items else None})
        (SITE / "c" / f"{s}.html").write_text(
            tpl_cat.render(cat={"name": n, "slug": s, "label": l, "date": date, "stale": stale, "products": items}, today=today, active=s, **common),
            encoding="utf-8",
        )

    # 골드박스 전체 페이지(탭)
    (SITE / "c" / "goldbox.html").write_text(
        tpl_cat.render(cat={"name": "골드박스", "slug": "goldbox", "label": "골드박스", "date": today, "stale": False, "products": latest["goldbox"], "is_goldbox": True}, today=today, active="goldbox", **common),
        encoding="utf-8",
    )

    tpl_index = env.get_template("index.html")
    (SITE / "index.html").write_text(
        tpl_index.render(latest=latest, posts=list(reversed(posts)), cats=cat_meta, active="home", **common), encoding="utf-8"
    )
    print(f"site/ 생성: 글 {len(posts)}개, 카테고리 탭 {len(cat_meta)}개 (오늘 성공 {sum(1 for c in cat_meta if not c['stale'] and c['count'])}), 최신 {today}")


if __name__ == "__main__":
    render()
