"""워드프레스 REST API 최소 클라이언트 — 응용 프로그램 비밀번호(Basic 인증).

필요한 것: 사이트 주소, 사용자명, 응용 프로그램 비밀번호(관리자 → 사용자 → 프로필 하단).
카테고리·태그는 이름으로 찾고 없으면 만든다. 글은 slug 로 찾아 있으면 갱신, 없으면 생성(멱등).
"""

from __future__ import annotations

import base64
import os
from typing import Any

import httpx


class WPError(RuntimeError):
    pass


class WordPress:
    def __init__(self, url: str | None = None, user: str | None = None, app_password: str | None = None, timeout: float = 30.0):
        self.url = (url or os.environ.get("WP_URL", "")).rstrip("/")
        user = user or os.environ.get("WP_USER", "")
        pw = app_password or os.environ.get("WP_APP_PASSWORD", "")
        if not (self.url and user and pw):
            raise WPError("WP_URL / WP_USER / WP_APP_PASSWORD 가 비어 있다 (.env 확인)")
        token = base64.b64encode(f"{user}:{pw}".encode()).decode()
        self._http = httpx.Client(
            headers={"Authorization": f"Basic {token}", "User-Agent": "todaydeal-bot/0.1"},
            timeout=timeout,
            follow_redirects=True,
        )
        # /wp-json 은 고유주소 리라이트가 살아 있어야 열린다. 안 열리면(공유호스팅·.htaccess 미생성)
        # 어디서나 되는 ?rest_route= 로 간다. (2026-09-10 로컬 실측: wp-cli 로 고유주소만 바꾸면 /wp-json 404)
        self._pretty = self._probe()

    def _probe(self) -> bool:
        try:
            r = self._http.get(self.url + "/wp-json/wp/v2/types", params={"_fields": "post"})
            r.json()
            return r.status_code == 200
        except Exception:
            return False

    def _u(self, path: str, params: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
        params = dict(params or {})
        if self._pretty:
            return self.url + "/wp-json/wp/v2" + path, params
        params["rest_route"] = "/wp/v2" + path
        return self.url + "/", params

    def _req(self, method: str, path: str, **kw: Any) -> Any:
        url, params = self._u(path, kw.pop("params", None))
        r = self._http.request(method, url, params=params, **kw)
        if r.status_code >= 400:
            raise WPError(f"{method} {path} → HTTP {r.status_code}: {r.text[:300]}")
        try:
            return r.json()
        except ValueError:
            raise WPError(f"{method} {path} → JSON 아님 (HTTP {r.status_code}): {r.text[:200]!r}") from None

    # ── 확인 ────────────────────────────────────────────────────────────
    def me(self) -> dict[str, Any]:
        return self._req("GET", "/users/me", params={"context": "edit"})

    # ── 분류 ────────────────────────────────────────────────────────────
    def ensure_term(self, kind: str, name: str, slug: str | None = None, parent: int | None = None) -> int:
        """kind: 'categories' | 'tags'. 이름(또는 slug)으로 찾고 없으면 생성 → id."""
        params: dict[str, Any] = {"search": name, "per_page": 100}
        for t in self._req("GET", f"/{kind}", params=params):
            if t["name"] == name or (slug and t["slug"] == slug):
                return int(t["id"])
        body: dict[str, Any] = {"name": name}
        if slug:
            body["slug"] = slug
        if parent:
            body["parent"] = parent
        return int(self._req("POST", f"/{kind}", json=body)["id"])

    # ── 글/페이지 (slug 멱등) ───────────────────────────────────────────
    def _find(self, kind: str, slug: str) -> dict[str, Any] | None:
        rows = self._req("GET", f"/{kind}", params={"slug": slug, "status": "publish,draft,future,private", "per_page": 1, "context": "edit"})
        return rows[0] if rows else None

    def upsert(self, kind: str, slug: str, title: str, content: str, *, status: str = "publish", categories: list[int] | None = None,
               tags: list[int] | None = None, excerpt: str | None = None, date: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        """kind: 'posts' | 'pages'. 같은 slug 가 있으면 내용만 갱신한다."""
        body: dict[str, Any] = {"slug": slug, "title": title, "content": content, "status": status}
        if categories is not None and kind == "posts":
            body["categories"] = categories
        if tags is not None and kind == "posts":
            body["tags"] = tags
        if excerpt is not None:
            body["excerpt"] = excerpt
        if date:
            body["date"] = date  # 사이트 로컬 시각 "YYYY-MM-DDTHH:MM:SS"
        if extra:
            body.update(extra)
        found = self._find(kind, slug)
        if found:
            return self._req("POST", f"/{kind}/{found['id']}", json=body)
        return self._req("POST", f"/{kind}", json=body)

    def close(self) -> None:
        self._http.close()
