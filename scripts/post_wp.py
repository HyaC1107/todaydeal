"""워드프레스에 오늘치 게시 — 일일 글 1개 + 카테고리 고정 페이지 8개 갱신 (전부 slug 멱등).

    uv run python scripts/post_wp.py            # data/ 최신 스냅샷 기준
    uv run python scripts/post_wp.py --collect  # 수집부터
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
load_dotenv(ROOT / ".env")

from coupang_deals.collect import TABS, collect  # noqa: E402
from coupang_deals.render_wp import all_category_names, category_page, daily_post  # noqa: E402
from coupang_deals.wp_client import WordPress  # noqa: E402

PARENT_CAT = "오늘딜"


def main() -> int:
    if "--collect" in sys.argv:
        print("collected:", collect().name)

    wp = WordPress()
    me = wp.me()
    print(f"WP 로그인: {me.get('name')} ({', '.join(me.get('roles', []))}) @ {wp.url}")

    # 카테고리: 오늘딜(부모) > 골드박스·식품·… (자식)
    parent = wp.ensure_term("categories", PARENT_CAT, slug="todaydeal")
    cat_ids = {"골드박스": wp.ensure_term("categories", "골드박스", slug="goldbox", parent=parent)}
    for name, slug, _ in TABS:
        cat_ids[name] = wp.ensure_term("categories", name, slug=slug, parent=parent)

    # 1) 일일 글
    slug, title, html, excerpt, d = daily_post()
    post = wp.upsert(
        "posts", slug, title, html,
        categories=[parent, cat_ids["골드박스"], cat_ids[d["category"]]],
        excerpt=excerpt,
        date=f"{d['date']}T09:00:00",
    )
    print(f"글: {post.get('link')}")

    # 2) 카테고리 고정 페이지 (매일 내용 갱신)
    for name in all_category_names():
        pslug, ptitle, phtml, pdate = category_page(name)
        page = wp.upsert("pages", pslug, ptitle, phtml)
        print(f"페이지: {ptitle:<10} {page.get('link')}  ({pdate})")
    wp.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
