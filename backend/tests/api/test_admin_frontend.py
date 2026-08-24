from pathlib import Path

import json

import pytest
from fastapi import Request
from fastapi import HTTPException

from app.api.admin import create_admin_router, issue_admin_session
from app.api.admin.root import has_admin_api_access
from app.api.admin_frontend import FRONTEND_INDEX_FILE, create_admin_frontend_router
from app.config import settings


def _get_route_endpoint(router, path: str, method: str):
    for route in router.routes:
        if getattr(route, "path", "") == path and method in getattr(
            route, "methods", set()
        ):
            return route.endpoint
    raise AssertionError(f"Route not found: {method} {path}")


def _build_request(path: str, cookies: dict | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
    }
    request = Request(scope)
    request._cookies = cookies or {}
    return request


def test_admin_frontend_dist_path_points_to_project_root() -> None:
    """后台静态入口应指向项目根目录下的构建产物。"""
    assert FRONTEND_INDEX_FILE.as_posix().endswith("web/admin/dist/index.html")
    assert FRONTEND_INDEX_FILE.parents[2].name == "web"


@pytest.mark.asyncio
async def test_admin_auth_me_returns_profile_with_cookie() -> None:
    router = create_admin_router(
        chat_service=object(),
        admin_service=object(),
        transfer_mgr=object(),
    )
    endpoint = _get_route_endpoint(router, "/api/v1/admin/me", "GET")

    payload = await endpoint(
        request=_build_request(
            "/api/v1/admin/me",
            cookies={"admin_session": issue_admin_session()},
        ),
    )

    body = json.loads(payload.body.decode())
    assert body["ok"] is True
    assert body["data"]["role"] == "admin"
    assert body["data"]["name"] == "管理员"


@pytest.mark.asyncio
async def test_admin_auth_me_accepts_bearer_token() -> None:
    router = create_admin_router(
        chat_service=object(),
        admin_service=object(),
        transfer_mgr=object(),
    )
    endpoint = _get_route_endpoint(router, "/api/v1/admin/me", "GET")

    payload = await endpoint(
        request=_build_request("/api/v1/admin/me"),
        authorization=f"Bearer {settings.ADMIN_API_TOKEN}",
    )

    body = json.loads(payload.body.decode())
    assert body["ok"] is True
    assert body["data"]["role"] == "admin"


def test_admin_bearer_is_disabled_without_explicit_compatibility_switch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """默认后台会话不接受长期 Bearer token。"""
    monkeypatch.setattr(settings, "ADMIN_ALLOW_LEGACY_BEARER", False)
    request = _build_request("/api/v1/admin/me")
    assert (
        has_admin_api_access(
            request, authorization=f"Bearer {settings.ADMIN_API_TOKEN}"
        )
        is False
    )


def test_admin_origin_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """后台凭证请求的跨站 Origin 必须被拒绝。"""
    monkeypatch.setattr(settings, "ADMIN_ALLOWED_ORIGINS", "https://admin.example")
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/admin/orders",
        "headers": [(b"origin", b"https://attacker.example")],
        "query_string": b"",
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
        "scheme": "http",
    }
    assert has_admin_api_access(Request(scope), authorization=None) is False


@pytest.mark.asyncio
async def test_admin_auth_login_sets_cookie() -> None:
    router = create_admin_router(
        chat_service=object(),
        admin_service=object(),
        transfer_mgr=object(),
    )
    endpoint = _get_route_endpoint(router, "/api/v1/admin/auth/login", "POST")

    async def receive() -> dict:
        return {
            "type": "http.request",
            "body": f'{{"token":"{settings.ADMIN_API_TOKEN}"}}'.encode("utf-8"),
            "more_body": False,
        }

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/admin/auth/login",
            "headers": [(b"content-type", b"application/json")],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
        },
        receive,
    )

    response = await endpoint(request)

    assert response.status_code == 200
    assert "admin_session=" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=strict" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_admin_login_rate_limits_failed_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """后台登录失败达到阈值后应暂时拒绝继续尝试。"""
    monkeypatch.setattr(settings, "ADMIN_LOGIN_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(settings, "ADMIN_LOGIN_WINDOW_SECONDS", 300)
    router = create_admin_router(
        chat_service=object(),
        admin_service=object(),
        transfer_mgr=object(),
    )
    endpoint = _get_route_endpoint(router, "/api/v1/admin/auth/login", "POST")

    async def invoke_invalid_login() -> None:
        async def receive() -> dict:
            return {
                "type": "http.request",
                "body": b'{"token":"invalid"}',
                "more_body": False,
            }

        request = Request(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/v1/admin/auth/login",
                "headers": [(b"content-type", b"application/json")],
                "query_string": b"",
                "server": ("testserver", 80),
                "client": ("rate-limit-client", 50000),
                "scheme": "http",
            },
            receive,
        )
        await endpoint(request)

    for _ in range(2):
        with pytest.raises(HTTPException) as error:
            await invoke_invalid_login()
        assert error.value.status_code == 401
    with pytest.raises(HTTPException) as error:
        await invoke_invalid_login()
    assert error.value.status_code == 429


@pytest.mark.asyncio
async def test_admin_route_returns_notice_when_dist_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    missing_dist = tmp_path / "missing-dist"
    monkeypatch.setattr("app.api.admin_frontend.FRONTEND_DIST_DIR", missing_dist)
    monkeypatch.setattr(
        "app.api.admin_frontend.FRONTEND_INDEX_FILE", missing_dist / "index.html"
    )

    router = create_admin_frontend_router()
    endpoint = _get_route_endpoint(router, "/admin", "GET")

    response = await endpoint()

    assert response.status_code == 503
    assert "admin 尚未构建" in response.body.decode("utf-8")
