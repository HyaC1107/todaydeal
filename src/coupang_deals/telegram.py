"""텔레그램 채널 발송.

아침(am): 오늘의 3개. 신호가 없는 날도 보내되 "신호 없음"을 정직하게 표기(초기엔 신호가 드물어
        아예 안 보내면 구독 습관이 안 생긴다 — 클또리 판단, 챗또리 자문 절충).
저녁(pm): 골드박스 재조회(API 1회) 후 **아침보다 가격이 오르지 않고 아직 있는 것만**, 그런 게 없으면 안 보낸다.
        아침 가격을 그대로 재전송하지 않는다(챗또리 자문 반영).
모든 메시지 첫 줄에 광고 표시. subid: tg-am / tg-pm.
"""

from __future__ import annotations

import html
import json
import os
from pathlib import Path
from typing import Any

import httpx

from .collect import EVENING, refresh_goldbox
from .render import CTA, build_context, decorate_day, with_sub_id

SITE_URL = os.environ.get("SITE_URL", "https://hyac1107.github.io/todaydeal/")
AD = "[광고] 쿠팡 파트너스 링크로 구매 시 수수료를 받습니다"


def _esc(s: str) -> str:
    return html.escape(str(s), quote=False)


def _line(it: dict[str, Any], sub: str, price_now: int | None = None) -> str:
    price = price_now if price_now is not None else it["price"]
    txt = f"<b>{_esc(it['name'][:48])}</b>\n   {price:,}원"
    if price_now is not None and price_now < it["price"]:
        txt += f" (아침 {it['price']:,}원보다 ▼)"
    if it["sig"]["vs_yesterday"] is not None and it["sig"]["vs_yesterday"] < 0:
        txt += f" · 어제보다 ▼{-it['sig']['vs_yesterday']}%"
    if it["sig"]["verdict"]:
        txt += f"\n   {_esc(it['sig']['verdict'])}"
    link = with_sub_id(it.get("url", ""), sub)
    return txt + f"\n   <a href=\"{link}\">{CTA}</a>"


def build_am() -> tuple[str, str | None]:
    prices, ranks, snaps = build_context()
    d = decorate_day(snaps[-1], prices, ranks, sub_prefix="tg")
    date_ko = f"{int(d['date'][5:7])}/{int(d['date'][8:10])} {d['weekday']}"
    items = d["picks"]
    has_signal = any(it["sig"]["verdict_kind"] in ("low", "near") or (it["sig"]["vs_yesterday"] or 0) < 0 for it in items)
    head = f"{AD}\n\n☀️ <b>{date_ko} 오늘의 3개</b>" + ("" if has_signal else "\n<i>오늘은 가격 하락 신호가 없어 골드박스 상위로 골랐습니다.</i>")
    tail = f"\n\n{d['category']} 베스트 10 + 골드박스 {len(d['goldbox'])}개 → {SITE_URL}"
    body = head + "\n\n" + "\n\n".join(_line(it, "tg-am") for it in items) + tail
    return body, (items[0].get("image") if items else None)


def build_pm(evening: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """재조회 결과가 없거나, 아침보다 안 오른 상품이 하나도 없으면 None(발송 안 함)."""
    prices, ranks, snaps = build_context()
    d = decorate_day(snaps[-1], prices, ranks, sub_prefix="tg")
    if not evening or evening.get("date") != d["date"]:
        return None, None
    now_by_id = {it["id"]: it for it in evening.get("goldbox", [])}
    keep = []
    for it in d["goldbox"]:
        cur = now_by_id.get(it["id"])
        if cur and cur["price"] <= it["price"]:
            keep.append((it, cur["price"]))
    if not keep:
        return None, None
    keep.sort(key=lambda x: (x[1] - x[0]["price"], x[0]["rank"]))  # 더 내린 것 먼저
    top = keep[:3]
    date_ko = f"{int(d['date'][5:7])}/{int(d['date'][8:10])} {d['weekday']}"
    head = f"{AD}\n\n🌙 <b>골드박스 자정 마감 — {date_ko} {evening.get('collected_at', '')[11:]} 재확인</b>\n<i>아침 가격에서 오르지 않은 것만 골랐습니다 ({len(keep)}/{len(d['goldbox'])}개)</i>"
    tail = f"\n\n골드박스 전체 → {SITE_URL}c/goldbox.html"
    body = head + "\n\n" + "\n\n".join(_line(it, "tg-pm", price_now=p) for it, p in top) + tail
    return body, top[0][0].get("image")


def build_message(slot: str) -> tuple[str | None, str | None]:
    if slot == "am":
        return build_am()
    evening = None
    try:
        p = refresh_goldbox()
        evening = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:  # 키 없음·API 실패 → 저녁은 보내지 않는다(아침 가격 재전송 금지)
        print(f"[pm] 골드박스 재조회 실패 → 발송 안 함: {str(e)[:120]}")
        cached = EVENING / f"{Path(p).stem}.json" if 'p' in dir() else None
        return None, None
    return build_pm(evening)


def send(slot: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    text, photo = build_message(slot)
    if text is None:
        print(f"[{slot}] 보낼 내용 없음 — 발송 건너뜀")
        return False
    if not token or not chat:
        print(f"[dry-run {slot}] 토큰/채널 없음 — 본문만:\n{text}\n(photo: {'있음' if photo else '없음'})")
        return False
    base = f"https://api.telegram.org/bot{token}"
    with httpx.Client(timeout=20) as c:
        if photo and len(text) <= 1000:
            r = c.post(f"{base}/sendPhoto", data={"chat_id": chat, "photo": photo, "caption": text, "parse_mode": "HTML"})
        else:
            r = c.post(f"{base}/sendMessage", data={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": "false"})
        ok = r.status_code == 200 and r.json().get("ok")
        print(f"telegram {slot}: {'OK' if ok else 'FAIL ' + r.text[:200]}")
        return bool(ok)
