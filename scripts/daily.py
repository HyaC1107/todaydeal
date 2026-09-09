"""매일 1회: 수집 → 사이트 생성. (텔레그램 발송은 토큰이 채워지면 붙는다.)"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from coupang_deals.collect import collect  # noqa: E402
from coupang_deals.render import render  # noqa: E402


def main() -> int:
    p = collect()
    print("collected:", p.name)
    render()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
