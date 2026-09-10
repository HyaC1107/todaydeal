"""WordPress.com OAuth2 토큰 발급 도우미 — 비밀번호를 어디에도 넣지 않는다.

1) https://developer.wordpress.com/apps/ 에서 앱 생성 → Client ID · Client Secret 을 .env 에:
       WPCOM_CLIENT_ID=...
       WPCOM_CLIENT_SECRET=...
       WPCOM_SITE=luvssol.wordpress.com
   Redirect URL 은 아래 REDIRECT 와 똑같이.
2) 실행:  uv run python scripts/wpcom_auth.py
   → 브라우저용 주소가 뜬다 → 사이트 소유 계정으로 로그인·승인 → 이동된 주소의 ?code=... 값을 붙여넣기
3) 토큰이 .env 의 WPCOM_TOKEN 에 저장된다(값은 화면에 안 찍힘). 토큰은 취소 전까지 유효.
"""

from __future__ import annotations

import io
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlencode

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ENV = ROOT / ".env"
REDIRECT = "https://hyac1107.github.io/todaydeal/"  # 앱 설정의 Redirect URL 과 일치해야 함


def _save_env(key: str, value: str) -> None:
    s = io.open(ENV, encoding="utf-8").read() if ENV.exists() else ""
    line = f'{key}="{value}"'
    if re.search(rf"^{key}=.*$", s, re.M):
        s = re.sub(rf"^{key}=.*$", line, s, flags=re.M)
    else:
        s = s.rstrip("\n") + f"\n{line}\n"
    io.open(ENV, "w", encoding="utf-8", newline="\n").write(s)


def main() -> int:
    load_dotenv(ENV)
    cid = os.environ.get("WPCOM_CLIENT_ID", "").strip()
    secret = os.environ.get("WPCOM_CLIENT_SECRET", "").strip()
    site = os.environ.get("WPCOM_SITE", "").strip()
    if not (cid and secret and site):
        print("WPCOM_CLIENT_ID / WPCOM_CLIENT_SECRET / WPCOM_SITE 를 .env 에 먼저 넣어라")
        return 2
    q = urlencode({"client_id": cid, "redirect_uri": REDIRECT, "response_type": "code", "blog": site, "scope": "global"})
    print("\n1) 이 주소를 브라우저에서 열고 승인:\n\n   https://public-api.wordpress.com/oauth2/authorize?" + q)
    print("\n2) 승인 후 이동된 주소에서 code= 뒤의 값을 붙여넣기:")
    code = input("   code> ").strip()
    if not code:
        return 2
    r = httpx.post(
        "https://public-api.wordpress.com/oauth2/token",
        data={"client_id": cid, "client_secret": secret, "redirect_uri": REDIRECT, "grant_type": "authorization_code", "code": code},
        timeout=30,
    )
    if r.status_code != 200:
        print("실패:", r.status_code, r.text[:300])
        return 1
    d = r.json()
    tok = d.get("access_token", "")
    _save_env("WPCOM_TOKEN", tok)
    print(f"\n토큰 저장 완료 → .env WPCOM_TOKEN ({len(tok)}자, blog_id={d.get('blog_id')}, scope={d.get('scope')})")
    me = httpx.get(f"https://public-api.wordpress.com/wp/v2/sites/{site}/users/me", headers={"Authorization": f"Bearer {tok}"}, params={"context": "edit"}, timeout=30)
    print("확인:", me.status_code, (me.json().get("name") if me.status_code == 200 else me.text[:200]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
