"""워드프레스용 HTML 생성 — 테마에 기대지 않는 인라인 스타일 카드.

산출물:
  daily_post(snap)      → (slug, title, html, excerpt)   일일 다이제스트 글 (아카이브·검색용)
  category_page(...)    → (slug, title, html)            카테고리 고정 페이지 (매일 내용만 갱신)
신호(가격·순위)는 render.py 의 계산을 그대로 쓴다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .collect import SLUG_OF, TABS
from .render import DATA, DISCLOSURE, _decorate, _latest_for_category, _load, _spark, _won

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
_env.filters["won"] = _won


def _ctx() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    prices = _load(DATA / "prices.json")
    ranks = _load(DATA / "ranks.json")
    snaps = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA / "snapshots").glob("*.json"))]
    if not snaps:
        raise SystemExit("data/snapshots 가 비어 있다 — collect 먼저")
    return prices, ranks, snaps


def daily_post(date: str | None = None) -> tuple[str, str, str, str, dict[str, Any]]:
    prices, ranks, snaps = _ctx()
    d = next((s for s in snaps if s["date"] == date), snaps[-1])
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
    title = f"{today[5:7]}/{today[8:10]} {d['weekday']}요일 {d['category']} 베스트 10 + 골드박스 {len(d['goldbox'])}"
    html = _env.get_template("wp_post.html").render(post=d, disclosure=DISCLOSURE)
    excerpt = f"{d['weekday']}요일 {d['category']} 베스트와 오늘의 골드박스. 어제 대비 가격·순위 변동 표시."
    return f"deal-{today}", title, html, excerpt, d


def category_page(name: str) -> tuple[str, str, str, str | None]:
    prices, ranks, snaps = _ctx()
    today = snaps[-1]["date"]
    if name == "골드박스":
        items = [dict(x) for x in snaps[-1]["goldbox"]]
        date = today
        _decorate(items, prices, ranks, None, today)
        slug = "goldbox"
    else:
        date, items = _latest_for_category(snaps, name)
        items = [dict(x) for x in items]
        _decorate(items, prices, ranks, name, date or today)
        slug = SLUG_OF[name]
    if items:
        items[0]["spark"] = _spark(prices, items[0]["id"], date or today)
    html = _env.get_template("wp_category.html").render(
        cat={"name": name, "products": items, "date": date, "stale": bool(date and date != today), "is_goldbox": name == "골드박스"},
        disclosure=DISCLOSURE,
    )
    title = "오늘의 골드박스" if name == "골드박스" else f"{name} 베스트"
    return slug, title, html, date


def all_category_names() -> list[str]:
    return ["골드박스"] + [n for n, _, _ in TABS]
