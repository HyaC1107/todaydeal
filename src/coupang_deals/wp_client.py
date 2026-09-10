"""워드프레스 REST 클라이언트 — 두 가지 모드.

A) 자체 호스팅(카페24 등): WP_URL + WP_USER + WP_APP_PASSWORD (Basic, 응용 프로그램 비밀번호)
B) WordPress.com 호스팅형:  WPCOM_SITE(예: luvssol.wordpress.com) + WPCOM_TOKEN (OAuth2 Bearer)
   → https://public-api.wordpress.com/wp/v2/sites/<site>/... (2026-09-10 실측: 사이트 직접 /wp-json 은 404)

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
    def __init__(self, timeout: float = 30.0):
        wpcom_site = os.environ.get("WPCOM_SITE", "").strip()
        wpcom_token = os.environ.get("WPCOM_TOKEN", "").strip()
        headers = {"User-Agent": "todaydeal-bot/0.2"}
        if wpcom_site and wpcom_token:
            self.mode = "wpcom"
            self.url = f"https://{wpcom_site}"
            self._api = f"https://public-api.wordpress.com/wp/v2/sites/{wpcom_site}"
            headers["Authorization"] = f"Bearer {wpcom_token}"
            self._pretty = True
        else:
            url = os.environ.get("WP_URL", "").rstrip("/")
            user = os.environ.get("WP_USER", "")
            pw = os.environ.get("WP_APP_PASSWORD", "")
            if not (url and user and pw):
                raise WPError("WPCOM_SITE+WPCOM_TOKEN 또는 WP_URL+WP_USER+WP_APP_PASSWORD 가 필요하다 (.env 확인)")
            self.mode = "selfhosted"
            self.url = url
            self._api = url + "/wp-json/wp/v2"
            headers["Authorization"] = "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode()
            self._pretty = None  # 첫 요청에서 판별
        self._http = httpx.Client(headers=headers, timeout=timeout, follow_redirects=True)

    def _probe(self) -> bool:
        try:
            r = self._http.get(self._api + "/types", params={"_fields": "post"})
            r.json()
            return r.status_code == 200
        except Exception:
            return False

    def _u(self, path: str, params: dict[str, Any] | None) -> tuple[str, dict[str, Any]]:
        params = dict(params or {})
        if self._pretty is None:
            self._pretty = self._probe()
        if self._pretty:
            return self._api + path, params
        params["rest_route"] = "/wp/v2" + path  # 자체호스팅에서 고유주소 리라이트가 죽었을 때
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

    def me(self) -> dict[str, Any]:
        return self._req("GET", "/users/me", params={"context": "edit"})

    def ensure_term(self, kind: str, name: str, slug: str | None = None, parent: int | None = None) -> int:
        for t in self._req("GET", f"/{kind}", params={"search": name, "per_page": 100}):
            if t["name"] == name or (slug and t["slug"] == slug):
                return int(t["id"])
        body: dict[str, Any] = {"name": name}
        if slug:
            body["slug"] = slug
        if parent:
            body["parent"] = parent
        return int(self._req("POST", f"/{kind}", json=body)["id"])

    def _find(self, kind: str, slug: str) -> dict[str, Any] | None:
        rows = self._req("GET", f"/{kind}", params={"slug": slug, "status": "publish,draft,future,private", "per_page": 1, "context": "edit"})
        return rows[0] if rows else None

    def upsert(self, kind: str, slug: str, title: str, content: str, *, status: str = "publish", categories: list[int] | None = None,
               tags: list[int] | None = None, excerpt: str | None = None, date: str | None = None, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"slug": slug, "title": title, "content": content, "status": status}
        if categories is not None and kind == "posts":
            body["categories"] = categories
        if tags is not None and kind == "posts":
            body["tags"] = tags
        if excerpt is not None:
            body["excerpt"] = excerpt
        if date:
            body["date"] = date
        if extra:
            body.update(extra)
        found = self._find(kind, slug)
        if found:
            return self._req("POST", f"/{kind}/{found['id']}", json=body)
        return self._req("POST", f"/{kind}", json=body)

    def close(self) -> None:
        self._http.close()
