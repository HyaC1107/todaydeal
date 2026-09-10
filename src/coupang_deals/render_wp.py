"""워드프레스용 HTML 생성 — 테마에 기대지 않는 인라인 스타일 카드. 신호·판정·오늘의 3개·subid는 render.py 와 공유."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .collect import SLUG_OF, TABS
from .render import CTA, DISCLOSURE, DISCLOSURE_TOP, OBS_NOTE, _decorate, _latest_for_category, _spark, _won, build_context, decorate_day

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
_env.filters["won"] = _won


def daily_post(date: str | None = None) -> tuple[str, str, str, str, dict[str, Any]]:
    prices, ranks, snaps = build_context()
    d = next((s for s in snaps if s["date"] == date), snaps[-1])
    decorate_day(d, prices, ranks, sub_prefix="wp")
    today = d["date"]
    title = f"{today[5:7]}/{today[8:10]} {d['weekday']}요일 {d['category']} 베스트 10 + 골드박스 {len(d['goldbox'])}"
    html = _env.get_template("wp_post.html").render(post=d, disclosure=DISCLOSURE, disclosure_top=DISCLOSURE_TOP, obs_note=OBS_NOTE, cta=CTA)
    excerpt = f"{d['weekday']}요일 {d['category']} 베스트와 오늘의 골드박스. 우리가 본 기간 중 최저가 판정, 어제 대비 가격·순위 변동."
    return f"deal-{today}", title, html, excerpt, d


def category_page(name: str) -> tuple[str, str, str, str | None]:
    prices, ranks, snaps = build_context()
    today = snaps[-1]["date"]
    if name == "골드박스":
        items = [dict(x) for x in snaps[-1]["goldbox"]]
        date = today
        _decorate(items, prices, ranks, None, today, "wp-gold")
        slug = "goldbox"
    else:
        date, items = _latest_for_category(snaps, name)
        items = [dict(x) for x in items]
        _decorate(items, prices, ranks, name, date or today, "wp-cat")
        slug = SLUG_OF[name]
    if items:
        items[0]["spark"] = _spark(prices, items[0]["id"], date or today, items[0].get("vid", ""))
    html = _env.get_template("wp_category.html").render(
        cat={"name": name, "products": items, "date": date, "stale": bool(date and date != today), "is_goldbox": name == "골드박스"},
        disclosure=DISCLOSURE, disclosure_top=DISCLOSURE_TOP, obs_note=OBS_NOTE, cta=CTA,
    )
    title = "오늘의 골드박스" if name == "골드박스" else f"{name} 베스트"
    return slug, title, html, date


def all_category_names() -> list[str]:
    return ["골드박스"] + [n for n, _, _ in TABS]
