"""키가 동작하는지 1회 확인 — 골드박스 조회. 키 값은 절대 출력하지 않는다."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from coupang_deals.coupang_api import CoupangError, CoupangPartners  # noqa: E402

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def main() -> int:
    try:
        api = CoupangPartners()
        items = api.goldbox()
    except CoupangError as e:
        print(f"FAIL {e}")
        return 1
    print(f"OK 골드박스 {len(items)}개")
    for it in items[:3]:
        name = str(it.get("productName", ""))[:40]
        print(f"  - {name} | {it.get('productPrice')}원 | 이미지: {'있음' if it.get('productImage') else '없음'} | 링크: {'있음' if it.get('productUrl') else '없음'}")
    if items:
        print("  응답 필드:", ", ".join(sorted(items[0].keys())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
