"""정적 사이트 생성 — data/ → site/.

페이지: index(오늘 요약·오늘의 3개) · posts/YYYY-MM-DD(일일 다이제스트) · c/<slug>(카테고리 탭) · goldbox
신호: 가격(어제보다·N일 최저·판정 한 줄) + 순위(어제 대비·연속 TOP10·신규). 전부 자체 이력에서 계산.
링크: 자리마다 subid 를 바꿔 붙인다(web-gold / web-best / web-pick …) → 파트너스 리포트에서 자리별 클릭·수수료 비교.
"""

from __future__ import annotations

import json
import re
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
# 표시광고 심사지침: 문자 매체는 첫 부분에 경제적 이해관계 표시. 상단·하단 둘 다 넣어 위치 논쟁을 없앤다.
DISCLOSURE_TOP = "광고 · 쿠팡 파트너스 링크로 구매 시 수수료를 받습니다"
OBS_NOTE = "가격·순위는 매일 09:17 KST 1회 관측한 값이며, \"최저가\"는 이 사이트가 저장한 기간 안에서 같은 판매자·옵션끼리 비교한 것입니다."
CTA = "쿠팡에서 가격 확인"


def _won(n: int) -> str:
    return f"{n:,}"


def _load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def with_sub_id(url: str, sub: str) -> str:
    """파트너스 링크의 subid 를 자리 태그로 교체한다(없으면 추가). 리포트에서 자리별로 갈라 본다."""
    if not url:
        return url
    if re.search(r"([?&])subid=[^&]*", url, re.I):
        return re.sub(r"([?&])subid=[^&]*", rf"\1subid={sub}", url, flags=re.I)
    return url + ("&" if "?" in url else "?") + f"subid={sub}"


# ── 신호 ──────────────────────────────────────────────────────────────
LEGACY_UNTIL = "2026-09-10"  # 이 날짜 이전 이력엔 vendorItemId가 없다(같은 productUrl 관측이라 동일 판매자로 간주)


def _same_item_history(rec: dict[str, Any], vid: str, today: str) -> list[tuple[str, int]]:
    """같은 판매자·옵션(vendorItemId)의 관측만. 옵션이 바뀐 상품을 같은 가격선에 놓지 않는다."""
    out = []
    for h in rec.get("history", []):
        d, p = h[0], h[1]
        if d > today:
            continue
        h_vid = h[2] if len(h) > 2 else ""
        if h_vid == vid or (not h_vid and d <= LEGACY_UNTIL) or not vid:
            out.append((d, p))
    return out


def _price_signals(prices: dict[str, Any], pid: str, price: int, today: str, vid: str = "") -> dict[str, Any]:
    """가격 이력 → 카드 신호 + 판정 한 줄. 이력이 하루면 조용히(첫날엔 아무 말 안 함)."""
    out: dict[str, Any] = {
        "vs_yesterday": None, "low30": False, "days": 0,
        "min_seen": None, "pct_over_min": None, "verdict": None, "verdict_kind": None,
    }
    rec = prices.get(pid)
    if not rec:
        return out
    hist = _same_item_history(rec, vid, today)
    out["days"] = len(hist)
    if len(hist) < 2:
        return out
    prev_price = hist[-2][1]
    if prev_price and prev_price != price:
        out["vs_yesterday"] = round((price - prev_price) / prev_price * 100)
    past = [p for d, p in hist if d != today and p > 0]
    if not past:
        return out
    mn = min(past)
    cutoff30 = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    w30 = [p for d, p in hist if cutoff30 <= d < today and p > 0]
    out["low30"] = bool(w30) and price <= min(w30)
    out["min_seen"] = mn
    pct = round((price - mn) / mn * 100)
    out["pct_over_min"] = pct
    n = len(hist)
    span_days = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(hist[0][0], "%Y-%m-%d")).days + 1
    # 판정 — 데이터로만 말한다. "쿠팡 최저가"가 아니라 "우리가 본 기간·관측 횟수 중". 매일 아침 1회 관측.
    if price <= mn:
        out["verdict"], out["verdict_kind"] = f"우리가 본 {span_days}일(관측 {n}회) 중 최저가", "low"
    elif pct <= 3:
        out["verdict"], out["verdict_kind"] = f"{span_days}일 최저가와 거의 같음 (+{pct}%)", "near"
    elif pct <= 10:
        out["verdict"], out["verdict_kind"] = f"{span_days}일 최저가보다 {pct}% 비쌈", "mid"
    else:
        out["verdict"], out["verdict_kind"] = f"{span_days}일 최저가보다 {pct}% 비쌈 — 기다리는 게 나음", "high"
    return out


def _rank_signals(ranks: dict[str, Any], cat: str, pid: str, rank: int, today: str) -> dict[str, Any]:
    out: dict[str, Any] = {"delta": None, "streak": 1, "new": False}
    bucket = ranks.get(cat) or {}
    hist = [(d, r) for d, r in bucket.get(pid, []) if d <= today]
    if len(hist) < 2:
        out["new"] = len(hist) == 1 and any(len(v) >= 2 for v in bucket.values())
        return out
    prev_date, prev_rank = hist[-2]
    yesterday = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    if prev_date == yesterday:
        out["delta"] = prev_rank - rank
    streak, cur = 1, datetime.strptime(today, "%Y-%m-%d")
    dates = {d for d, _ in hist}
    while (cur - timedelta(days=1)).strftime("%Y-%m-%d") in dates:
        streak += 1
        cur -= timedelta(days=1)
    out["streak"] = streak
    return out


def _spark(prices: dict[str, Any], pid: str, today: str, vid: str = "") -> list[tuple[str, int]]:
    rec = prices.get(pid)
    return _same_item_history(rec, vid, today)[-30:] if rec else []


def _decorate(items: list[dict[str, Any]], prices: dict[str, Any], ranks: dict[str, Any], cat: str | None, today: str, sub: str) -> None:
    for it in items:
        it["sig"] = _price_signals(prices, it["id"], it["price"], today, it.get("vid", ""))
        it["rk"] = _rank_signals(ranks, cat, it["id"], it["rank"], today) if cat else {"delta": None, "streak": 1, "new": False}
        it["link"] = with_sub_id(it.get("url", ""), sub)


def _score(it: dict[str, Any]) -> float:
    """오늘의 3개 고르기 — 내린 폭·최저가·순위 급등에 점수. 첫날(신호 없음)은 골드박스 순위."""
    s = it["sig"]
    sc = 0.0
    if s["verdict_kind"] == "low":
        sc += 50
    if s["low30"]:
        sc += 20
    if s["vs_yesterday"] is not None and s["vs_yesterday"] < 0:
        sc += min(40, -s["vs_yesterday"] * 2)
    d = it["rk"].get("delta")
    if d:
        sc += max(0, min(15, d * 3))
    if it["rk"].get("new"):
        sc += 5
    return sc


def pick_top3(goldbox: list[dict[str, Any]], best: list[dict[str, Any]]) -> list[dict[str, Any]]:
    pool = goldbox + best
    scored = sorted(pool, key=_score, reverse=True)
    if scored and _score(scored[0]) > 0:
        picks, seen = [], set()
        for it in scored:
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            picks.append(it)
            if len(picks) == 3:
                break
        return picks
    return goldbox[:3]  # 첫날: 신호가 없으니 골드박스 상위


def _latest_for_category(snaps: list[dict[str, Any]], cat: str) -> tuple[str | None, list[dict[str, Any]]]:
    for d in reversed(snaps):
        lst = d.get("categories", {}).get(cat) or (d.get("best") if d.get("category") == cat else None)
        if lst:
            return d["date"], lst
    return None, []


# ── 빌드 ──────────────────────────────────────────────────────────────
def build_context() -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    prices = _load(DATA / "prices.json")
    ranks = _load(DATA / "ranks.json")
    snaps = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((DATA / "snapshots").glob("*.json"))]
    if not snaps:
        raise SystemExit("data/snapshots 가 비어 있다 — collect 먼저")
    return prices, ranks, snaps


def decorate_day(d: dict[str, Any], prices: dict[str, Any], ranks: dict[str, Any], *, sub_prefix: str) -> dict[str, Any]:
    """스냅샷 하루치에 신호·링크·요약·오늘의 3개를 붙인다. sub_prefix: 'web' | 'wp' | 'tg'."""
    today = d["date"]
    _decorate(d["goldbox"], prices, ranks, None, today, f"{sub_prefix}-gold")
    _decorate(d["best"], prices, ranks, d["category"], today, f"{sub_prefix}-best")
    if d["goldbox"]:
        d["goldbox"][0]["spark"] = _spark(prices, d["goldbox"][0]["id"], today, d["goldbox"][0].get("vid", ""))
    picks = [dict(x) for x in pick_top3(d["goldbox"], d["best"])]
    for p in picks:
        p["link"] = with_sub_id(p.get("url", ""), f"{sub_prefix}-pick")
        p["spark"] = _spark(prices, p["id"], today, p.get("vid", ""))
    d["picks"] = picks
    allitems = d["goldbox"] + d["best"]
    d["summary"] = {
        "drop": sum(1 for it in allitems if (it["sig"]["vs_yesterday"] or 0) < 0),
        "low": sum(1 for it in allitems if it["sig"]["verdict_kind"] == "low"),
    }
    d["title"] = f"{d['weekday']}요일 {d['category']} 베스트 10 + 골드박스 {len(d['goldbox'])}"
    d["slug"] = SLUG_OF.get(d["category"], "")
    return d


def render() -> None:
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=select_autoescape(["html"]))
    env.filters["won"] = _won
    prices, ranks, snaps = build_context()

    if SITE.exists():
        shutil.rmtree(SITE)
    (SITE / "posts").mkdir(parents=True)
    (SITE / "c").mkdir()
    shutil.copy(TEMPLATES / "style.css", SITE / "style.css")
    (SITE / ".nojekyll").write_text("", encoding="utf-8")

    tabs = [{"name": n, "slug": s, "label": l} for n, s, l in TABS]
    common = {"site": SITE_NAME, "disclosure": DISCLOSURE, "disclosure_top": DISCLOSURE_TOP, "obs_note": OBS_NOTE, "tabs": tabs, "cta": CTA}

    posts = [decorate_day(d, prices, ranks, sub_prefix="web") for d in snaps]
    latest = posts[-1]
    today = latest["date"]

    tpl_post = env.get_template("post.html")
    for d in posts:
        (SITE / "posts" / f"{d['date']}.html").write_text(tpl_post.render(post=d, active="post", **common), encoding="utf-8")

    tpl_cat = env.get_template("category.html")
    cat_meta: list[dict[str, Any]] = []
    for n, s, l in TABS:
        date, items = _latest_for_category(snaps, n)
        items = [dict(x) for x in items]
        _decorate(items, prices, ranks, n, date or today, "web-cat")
        if items:
            items[0]["spark"] = _spark(prices, items[0]["id"], date or today, items[0].get("vid", ""))
        stale = bool(date and date != today)
        cat_meta.append({"name": n, "slug": s, "label": l, "date": date, "count": len(items), "stale": stale, "top": items[0] if items else None})
        (SITE / "c" / f"{s}.html").write_text(
            tpl_cat.render(cat={"name": n, "slug": s, "label": l, "date": date, "stale": stale, "products": items}, today=today, active=s, **common),
            encoding="utf-8",
        )
    (SITE / "c" / "goldbox.html").write_text(
        tpl_cat.render(cat={"name": "골드박스", "slug": "goldbox", "label": "골드박스", "date": today, "stale": False, "products": latest["goldbox"], "is_goldbox": True}, today=today, active="goldbox", **common),
        encoding="utf-8",
    )

    tpl_index = env.get_template("index.html")
    (SITE / "index.html").write_text(
        tpl_index.render(latest=latest, posts=list(reversed(posts)), cats=cat_meta, active="home", **common), encoding="utf-8"
    )
    print(f"site/ 생성: 글 {len(posts)}개, 탭 {len(cat_meta)}개, 오늘의 3개 {[p['name'][:12] for p in latest['picks']]}")


if __name__ == "__main__":
    render()
