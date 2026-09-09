"""정적 사이트 생성 — data/ → site/. 가격 이력으로 '어제보다 ▼' · '30일 최저가' 신호를 만든다."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SITE = ROOT / "site"
TEMPLATES = ROOT / "templates"
SITE_NAME = "오늘딜"
DISCLOSURE = "이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다."


def _won(n: int) -> str:
    return f"{n:,}"


def _signals(prices: dict[str, Any], pid: str, price: int, today: str) -> dict[str, Any]:
    """가격 이력 → 카드에 붙일 신호. 이력이 하루뿐이면 아무 신호도 없다(첫날엔 조용히)."""
    rec = prices.get(pid)
    out: dict[str, Any] = {"vs_yesterday": None, "low30": False, "low30_price": None, "days": 0}
    if not rec:
        return out
    hist = [(d, p) for d, p in rec["history"] if d <= today]
    out["days"] = len(hist)
    if len(hist) < 2:
        return out
    prev_date, prev_price = hist[-2]
    if prev_price and prev_price != price:
        out["vs_yesterday"] = round((price - prev_price) / prev_price * 100)
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    window = [p for d, p in hist if d >= cutoff and d != today]
    if window and price <= min(window):
        out["low30"] = True
        out["low30_price"] = min(window)
    return out


def _spark(prices: dict[str, Any], pid: str, today: str) -> list[tuple[str, int]]:
    rec = prices.get(pid)
    if not rec:
        return []
    return [(d, p) for d, p in rec["history"] if d <= today][-30:]


def render() -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    env.filters["won"] = _won
    prices = json.loads((DATA / "prices.json").read_text(encoding="utf-8")) if (DATA / "prices.json").exists() else {}
    snaps = sorted((DATA / "snapshots").glob("*.json"))
    if not snaps:
        raise SystemExit("data/snapshots 가 비어 있다 — collect 먼저")

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "posts").mkdir(parents=True)
    shutil.copy(TEMPLATES / "style.css", SITE / "style.css")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")

    posts: list[dict[str, Any]] = []
    for sp in snaps:
        d = json.loads(sp.read_text(encoding="utf-8"))
        today = d["date"]
        for it in d["goldbox"] + d["best"]:
            it["sig"] = _signals(prices, it["id"], it["price"], today)
        # 1위 골드박스엔 30일 스파크라인
        if d["goldbox"]:
            d["goldbox"][0]["spark"] = _spark(prices, d["goldbox"][0]["id"], today)
        n_drop = sum(1 for it in d["goldbox"] + d["best"] if (it["sig"]["vs_yesterday"] or 0) < 0)
        n_low = sum(1 for it in d["goldbox"] + d["best"] if it["sig"]["low30"])
        d["summary"] = {"drop": n_drop, "low": n_low}
        d["title"] = f"{d['weekday']}요일 {d['category']} 베스트 10 + 골드박스 {len(d['goldbox'])}"
        posts.append(d)

    tpl_post = env.get_template("post.html")
    tpl_index = env.get_template("index.html")
    common = {"site": SITE_NAME, "disclosure": DISCLOSURE}
    for d in posts:
        (SITE / "posts" / f"{d['date']}.html").write_text(tpl_post.render(post=d, **common), encoding="utf-8")
    latest = posts[-1]
    (SITE / "index.html").write_text(
        tpl_index.render(latest=latest, posts=list(reversed(posts)), **common), encoding="utf-8"
    )
    print(f"site/ 생성: 글 {len(posts)}개, 최신 {latest['date']}")


if __name__ == "__main__":
    render()
