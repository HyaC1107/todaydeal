"""쿠팡 파트너스 Open API 최소 클라이언트.

인증: HMAC-SHA256. 서명 메시지 = 시각 + HTTP메서드 + 경로 + 쿼리(물음표 제외).
시각은 UTC를 ``yyMMddTHHmmssZ`` 로 찍는다(초 단위, 서버와 몇 분 이상 어긋나면 401).

엔드포인트(모두 ``/v2/providers/affiliate_open_api/apis/openapi/v1`` 아래):
    GET  /products/goldbox                     오늘의 골드박스
    GET  /products/bestcategories/{categoryId}  카테고리 베스트 (limit, subId)
    GET  /products/search?keyword=&limit=       검색
    POST /deeplink  {"coupangUrls": [...]}      수익 링크 변환
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from typing import Any

import httpx

DOMAIN = "https://api-gateway.coupang.com"
BASE = "/v2/providers/affiliate_open_api/apis/openapi/v1"

#: 카테고리 ID (파트너스 문서 기준). 요일별 스케줄에서 쓴다.
CATEGORIES: dict[str, int] = {
    "여성패션": 1001, "남성패션": 1002, "뷰티": 1010, "출산유아동": 1011,
    "식품": 1012, "주방용품": 1013, "생활용품": 1014, "홈인테리어": 1015,
    "가전디지털": 1016, "스포츠레저": 1017, "자동차용품": 1018, "도서음반DVD": 1019,
    "완구취미": 1020, "문구오피스": 1021, "헬스건강식품": 1024, "국내여행": 1025,
    "해외여행": 1026, "반려동물용품": 1029, "유아동패션": 1030,
}


class CoupangError(RuntimeError):
    pass


class CoupangPartners:
    def __init__(self, access_key: str | None = None, secret_key: str | None = None, timeout: float = 15.0):
        self.access_key = access_key or os.environ.get("COUPANG_ACCESS_KEY", "")
        self.secret_key = secret_key or os.environ.get("COUPANG_SECRET_KEY", "")
        if not self.access_key or not self.secret_key:
            raise CoupangError("COUPANG_ACCESS_KEY / COUPANG_SECRET_KEY 가 비어 있다 (.env 확인)")
        self._http = httpx.Client(base_url=DOMAIN, timeout=timeout)

    # ── 인증 ────────────────────────────────────────────────────────────
    def _auth_header(self, method: str, path: str, query: str) -> str:
        signed_date = datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")
        message = signed_date + method + path + query
        signature = hmac.new(self.secret_key.encode(), message.encode(), hashlib.sha256).hexdigest()
        return (
            f"CEA algorithm=HmacSHA256, access-key={self.access_key}, "
            f"signed-date={signed_date}, signature={signature}"
        )

    def _request(self, method: str, path: str, params: dict[str, Any] | None = None, body: Any = None) -> Any:
        full_path = BASE + path
        query = "&".join(f"{k}={v}" for k, v in (params or {}).items() if v is not None)
        url = full_path + (f"?{query}" if query else "")
        headers = {"Authorization": self._auth_header(method, full_path, query), "Content-Type": "application/json"}
        r = self._http.request(method, url, headers=headers, content=json.dumps(body) if body is not None else None)
        if r.status_code != 200:
            raise CoupangError(f"HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        # 응답 봉투: {"rCode": "0", "rMessage": "", "data": [...]}
        if str(data.get("rCode")) != "0":
            raise CoupangError(f"rCode={data.get('rCode')} {data.get('rMessage')}")
        return data.get("data")

    # ── 공개 ────────────────────────────────────────────────────────────
    def goldbox(self, sub_id: str | None = None) -> list[dict[str, Any]]:
        return self._request("GET", "/products/goldbox", {"subId": sub_id}) or []

    def best_category(self, category_id: int, limit: int = 20, sub_id: str | None = None) -> list[dict[str, Any]]:
        return self._request("GET", f"/products/bestcategories/{category_id}", {"limit": limit, "subId": sub_id}) or []

    def search(self, keyword: str, limit: int = 10, sub_id: str | None = None) -> list[dict[str, Any]]:
        d = self._request("GET", "/products/search", {"keyword": keyword, "limit": limit, "subId": sub_id})
        return (d or {}).get("productData", []) if isinstance(d, dict) else (d or [])

    def deeplink(self, urls: list[str], sub_id: str | None = None) -> list[dict[str, Any]]:
        body: dict[str, Any] = {"coupangUrls": urls}
        if sub_id:
            body["subId"] = sub_id
        return self._request("POST", "/deeplink", body=body) or []

    def close(self) -> None:
        self._http.close()
