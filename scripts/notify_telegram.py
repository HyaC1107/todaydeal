"""텔레그램 발송.  uv run python scripts/notify_telegram.py am|pm   (토큰 없으면 드라이런)"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from coupang_deals.telegram import send  # noqa: E402

if __name__ == "__main__":
    slot = sys.argv[1] if len(sys.argv) > 1 else "am"
    send(slot)
