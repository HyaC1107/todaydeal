"""텔레그램 채널 발송 — 아침(오늘의 3개) · 저녁(골드박스 자정 마감). 토큰 없으면 드라이런으로 본문만 출력.

subid: tg-am / tg-pm — 리포트에서 아침·저녁 어느 쪽이 클릭·수수료가 나오는지 가른다.
"""

from __future__ import annotations

import html
import os
from typing import Any

import httpx

from .render import CTA, build_context, decorate_day, with_sub_id

SITE_URL = os.environ.get("SITE_URL", "https://hyac1107.github.io/todaydeal/")


def _esc(s: str) -> str:
    return html.escape(str(s), quote=False)


def _line(it: dict[str, Any], sub: str) -> str:
    price = f"{it['price']:,}원"
    extra = ""
    if it["sig"]["vs_yesterday"] is not None and it["sig"]["vs_yesterday"] < 0:
        extra += f" · 어제보다 ▼{-it['sig']['vs_yesterday']}%"
    if it["sig"]["verdict"]:
        extra += f"\n   {_esc(it['sig']['verdict'])}"
    link = with_sub_id(it.get("url", ""), sub)
    return f"<b>{_esc(it['name'][:48])}</b>\n   {price}{extra}\n   <a href=\"{link}\">{CTA}</a>"


def build_message(slot: str) -> tuple[str, str | None]:
    """slot: 'am' | 'pm' → (HTML 본문, 사진 URL)."""
    prices, ranks, snaps = build_context()
    d = decorate_day(snaps[-1], prices, ranks, sub_prefix="tg")
    date_ko = f"{int(d['date'][5:7])}/{int(d['date'][8:10])} {d['weekday']}"
    if slot == "am":
        items = d["picks"]
        head = f"☀️ <b>{date_ko} 오늘의 3개</b>"
        tail = f"\n\n오늘 {d['category']} 베스트 10 + 골드박스 {len(d['goldbox'])}개 → {SITE_URL}"
        sub = "tg-am"
    else:
        items = d["goldbox"][:3]
        head = f"🌙 <b>골드박스 자정 마감 3시간 전</b> — {date_ko}"
        tail = f"\n\n골드박스 전체 {len(d['goldbox'])}개 → {SITE_URL}c/goldbox.html"
        sub = "tg-pm"
    body = head + "\n\n" + "\n\n".join(_line(it, sub) for it in items) + tail
    body += "\n\n<i>쿠팡 파트너스 활동의 일환으로 수수료를 제공받습니다.</i>"
    photo = items[0].get("image") if items else None
    return body, photo


def send(slot: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat = os.environ.get("TELEGRAM_CHANNEL_ID", "").strip()
    text, photo = build_message(slot)
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
