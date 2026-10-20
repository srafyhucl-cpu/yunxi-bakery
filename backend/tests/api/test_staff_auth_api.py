"""店员认证 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.staff.auth import create_staff_auth_router
from app.config import settings
from app.database import close_db, init_db
from app.repository.staff_repo import StaffAuditRepo, StaffRepo
from app.service.staff_auth import StaffAuthService


@pytest.fixture
def auth_service(db: aiosqlite.Connection) -> StaffAuthService:
    return StaffAuthService(
        staff_repo=StaffRepo(db),
        audit_repo=StaffAuditRepo(db),
    )


@pytest.fixture
def login_events(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[str]]:
    """隔离真实边缘防护库，记录限流与清理调用。"""
    events: dict[str, list[str]] = {"attempt": [], "clear": []}

    async def allow(key: str) -> bool:
        events["attempt"].append(key)
        return True

    async def clear(key: str) -> None:
        events["clear"].append(key)

    monkeypatch.setattr("app.api.staff.auth.attempt_admin_login", allow)
    monkeypatch.setattr("app.api.staff.auth.clear_admin_login_failures", clear)
    return events


@pytest.fixture
def app(auth_service: StaffAuthService, login_events: dict) -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(create_staff_auth_router(auth_service))
    return test_app


@pytest.mark.asyncio
async def test_staff_login_sets_cookie_and_me_reads_principal(
    app: FastAPI,
    auth_service: StaffAuthService,
    login_events: dict,
) -> None:
    account = await auth_service.create_staff("小王", "13800000001", "cashier", "2468")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/staff/auth/login",
            json={"phone": "13800000001", "pin": "2468"},
        )
        assert response.status_code == 200
        assert response.json()["data"] == {
            "staffId": account.id,
            "name": "小王",
            "role": "cashier",
        }
        assert client.cookies.get("staff_session")

        me_response = await client.get("/api/v1/staff/auth/me")
        assert me_response.status_code == 200
        assert me_response.json()["data"]["staffId"] == account.id
        assert me_response.json()["data"]["tenantId"] == "yunxi"

        logout_response = await client.post("/api/v1/staff/auth/logout")
        assert logout_response.status_code == 200
        after_logout = await client.get("/api/v1/staff/auth/me")

    assert after_logout.status_code == 401
    assert login_events["clear"]


@pytest.mark.asyncio
async def test_staff_login_rejects_wrong_pin_and_records_attempt(
    app: FastAPI,
    auth_service: StaffAuthService,
    login_events: dict,
) -> None:
    await auth_service.create_staff("小李", "13800000002", "manager", "1357")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/staff/auth/login",
            json={"phone": "13800000002", "pin": "0000"},
        )

    assert response.status_code == 401
    assert "staff_session" not in response.cookies
    assert login_events["attempt"]
    assert login_events["attempt"][0].startswith("staff:")


@pytest.mark.asyncio
async def test_staff_login_rate_limit_counts_each_failure_once_and_clears_on_success(
    auth_service: StaffAuthService,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """一次失败只计一次：3 次错误后第 4 次 429，成功登录会清零计数。"""
    await auth_service.create_staff("小周", "13800000009", "cashier", "2468")
    monkeypatch.setattr(settings, "EDGE_PROTECTION_BACKEND", "sqlite")
    monkeypatch.setattr(settings, "ADMIN_LOGIN_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(settings, "ADMIN_LOGIN_WINDOW_SECONDS", 300)
    rate_db = tmp_path / "staff_rate_limit.db"
    monkeypatch.setattr(settings, "DB_PATH", str(rate_db))
    connection = await init_db(str(rate_db))
    await close_db(connection)

    test_app = FastAPI()
    test_app.include_router(create_staff_auth_router(auth_service))
    transport = httpx.ASGITransport(app=test_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:

        async def login(pin: str) -> httpx.Response:
            return await client.post(
                "/api/v1/staff/auth/login",
                json={"phone": "13800000009", "pin": pin},
            )

        assert (await login("2468")).status_code == 200
        # 成功登录后计数已清零；两次失败不会提前触发阈值。
        assert (await login("0000")).status_code == 401
        assert (await login("0000")).status_code == 401
        assert (await login("2468")).status_code == 200
        # 清零后重新累计：连续 3 次失败均为 401，第 4 次才被限流。
        assert (await login("0000")).status_code == 401
        assert (await login("0000")).status_code == 401
        assert (await login("0000")).status_code == 401
        assert (await login("0000")).status_code == 429


@pytest.mark.asyncio
async def test_staff_login_succeeds_with_real_rate_limit_on_same_sqlite_file(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实限流函数 + 真实 SQLite 文件库：登录成功必须返回 200，不得出现写锁互锁。

    回归场景：请求连接写完「最后登录时间 + 登录审计」后未提交，仍持有 SQLite 写锁；
    随后的 clear_admin_login_failures 另开连接写同一个库文件，等满 busy_timeout
    后抛 "database is locked"，登录接口退化为 500。
    """
    db_path = tmp_path / "staff_login_write_lock.db"
    monkeypatch.setattr(settings, "DB_PATH", str(db_path))
    monkeypatch.setattr(settings, "EDGE_PROTECTION_BACKEND", "sqlite")
    monkeypatch.setattr(settings, "ADMIN_LOGIN_MAX_ATTEMPTS", 5)
    monkeypatch.setattr(settings, "ADMIN_LOGIN_WINDOW_SECONDS", 300)

    # 请求级连接与限流连接指向同一个库文件，才能真实复现写锁互锁。
    request_conn = await init_db(str(db_path))
    service = StaffAuthService(
        staff_repo=StaffRepo(request_conn),
        audit_repo=StaffAuditRepo(request_conn),
    )
    await service.create_staff("小赵", "13800000010", "cashier", "2468")
    await request_conn.commit()

    test_app = FastAPI()
    test_app.include_router(create_staff_auth_router(service))
    # 与生产一致：未预期异常统一转 500，而不是直接抛给调用方。
    transport = httpx.ASGITransport(app=test_app, raise_app_exceptions=False)
    try:
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as client:
            response = await client.post(
                "/api/v1/staff/auth/login",
                json={"phone": "13800000010", "pin": "2468"},
            )
    finally:
        await close_db(request_conn)

    assert response.status_code == 200, response.text
    assert "database is locked" not in response.text
    assert response.json()["data"]["name"] == "小赵"
    assert response.cookies.get("staff_session")

    # 登录状态必须已经落库（证明写锁已释放，别的连接能立刻读到）。
    verify_conn = await init_db(str(db_path))
    try:
        account_rows = await verify_conn.execute_fetchall(
            "SELECT last_login_at FROM staff_accounts WHERE phone = ?",
            ("13800000010",),
        )
        attempt_rows = await verify_conn.execute_fetchall(
            "SELECT client_key FROM admin_login_attempts",
        )
        audit_rows = await verify_conn.execute_fetchall(
            "SELECT action FROM staff_audit_logs WHERE action = ?",
            ("login",),
        )
    finally:
        await close_db(verify_conn)

    assert account_rows and account_rows[0][0]
    assert attempt_rows == []
    assert len(audit_rows) == 1


@pytest.mark.asyncio
async def test_staff_login_rate_limit_returns_429(
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def reject(_key: str) -> bool:
        return False

    monkeypatch.setattr("app.api.staff.auth.attempt_admin_login", reject)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/staff/auth/login",
            json={"phone": "13800000001", "pin": "2468"},
        )

    assert response.status_code == 429


@pytest.mark.asyncio
async def test_staff_login_fails_closed_without_session_secret(
    app: FastAPI,
    auth_service: StaffAuthService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await auth_service.create_staff("小陈", "13800000003", "cashier", "4321")
    monkeypatch.setattr(settings, "STAFF_SESSION_SECRET", "")

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/staff/auth/login",
            json={"phone": "13800000003", "pin": "4321"},
        )

    assert response.status_code == 503
