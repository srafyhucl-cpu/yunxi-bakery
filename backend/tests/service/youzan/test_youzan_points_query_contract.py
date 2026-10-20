"""有赞积分查询取数契约测试。

锁死 2026-10-20 生产实测的三条事实（证据见
`backend/scripts/reconcile_youzan_points_dead_letters.py` 与
`docs/release/stage-5.2-production-cutover.md`）：

1. `youzan.crm.customer.points.get` 的可用版本是 **1.0.0**；3.0.0 会被有赞
   网关以 4005「非法的API」拒绝，调用结果恒为空字典，会让会员导入把积分
   锚点写成 0；
2. 请求体必须是 `user.account_type=2`（手机号）+ `user.account_id=手机号`，
   积分余额从响应的 `data.point` 读取；
3. 查不到数据（空响应 / 接口报错）时**不得**伪造 0 积分：调用方必须跳过
   积分镜像，不得把「未知」写成 0 清空会员已有的积分锚点。
"""

import aiosqlite
import pytest

from app.config import settings
from app.service.member_loyalty import MemberLoyaltyImportService
from app.service.youzan.member_api import (
    POINTS_QUERY_API_NAME,
    POINTS_QUERY_API_VERSION,
    YouzanMemberApi,
)

MOBILE = "13800004001"


class RecordingYouzanClient:
    """记录每次 OpenAPI 调用的假客户端。"""

    def __init__(self, points_response: dict) -> None:
        self._points_response = points_response
        self.calls: list[tuple[str, str, dict]] = []

    async def call_api(self, api_name: str, version: str, params: dict) -> dict:
        self.calls.append((api_name, version, params))
        if api_name == POINTS_QUERY_API_NAME:
            return self._points_response
        return {"data": {}}


@pytest.mark.asyncio
async def test_points_query_uses_version_1_0_0_and_mobile_account(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """积分查询必须打 1.0.0，并按手机号口径传参。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = RecordingYouzanClient(
        {"code": 200, "success": True, "data": {"point": 16376}}
    )

    payload = await YouzanMemberApi(client).query_points(MOBILE)

    assert POINTS_QUERY_API_VERSION == "1.0.0"
    assert len(client.calls) == 1
    api_name, version, params = client.calls[0]
    assert api_name == "youzan.crm.customer.points.get"
    assert version == "1.0.0"
    assert params["user"] == {"account_type": 2, "account_id": MOBILE}
    # 旧的扁平参数（有赞会判为非法参数）不得回流。
    assert "mobile" not in params
    assert "kdt_id" not in params
    # 官方响应形状是 `data.point`，取数层原样透出。
    assert payload == {"point": 16376}


@pytest.mark.asyncio
async def test_import_writes_anchor_from_data_point(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`data.point` 必须被解析成整数并写成积分锚点。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = RecordingYouzanClient(
        {"code": 200, "success": True, "data": {"point": 16376}}
    )
    service = MemberLoyaltyImportService(db, client, tenant_id="yunxi")

    stats = await service.import_one(MOBILE, customer_id="cust-1", should_apply=True)

    assert stats["points_total"] == 16376
    assert stats["errors"] == []
    rows = await db.execute_fetchall(
        "SELECT points, youzan_points_base FROM member_balance WHERE mobile = ?",
        (MOBILE,),
    )
    assert len(rows) == 1
    assert int(rows[0]["points"]) == 16376
    assert int(rows[0]["youzan_points_base"]) == 16376


@pytest.mark.asyncio
async def test_zero_points_response_is_authoritative_value(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`data.point=0` 是权威的 0 分，不得当成「查不到」而跳过写入。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = RecordingYouzanClient({"code": 200, "success": True, "data": {"point": 0}})
    service = MemberLoyaltyImportService(db, client, tenant_id="yunxi")

    stats = await service.import_one(MOBILE, customer_id="cust-1", should_apply=True)

    assert stats["points_total"] == 0
    assert stats["errors"] == []
    rows = await db.execute_fetchall(
        "SELECT points, youzan_points_base FROM member_balance WHERE mobile = ?",
        (MOBILE,),
    )
    assert len(rows) == 1
    assert int(rows[0]["points"]) == 0
    assert int(rows[0]["youzan_points_base"]) == 0


@pytest.mark.asyncio
async def test_empty_response_must_not_fabricate_zero_points(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """空响应时不得把积分写成 0，也不得凭空建出余额行。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = RecordingYouzanClient({})
    service = MemberLoyaltyImportService(db, client, tenant_id="yunxi")

    stats = await service.import_one(MOBILE, customer_id="cust-1", should_apply=True)

    assert stats["points_total"] == 0
    # 「有赞侧未知」必须显式暴露，不得与「确实是 0 分」混为一谈。
    assert stats["errors"]
    rows = await db.execute_fetchall(
        "SELECT points FROM member_balance WHERE mobile = ?", (MOBILE,)
    )
    assert rows == []


@pytest.mark.asyncio
async def test_gateway_error_must_not_zero_existing_anchor(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """接口报错时已有积分锚点必须原样保留，不得被 0 覆盖。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    await db.execute(
        "INSERT INTO member_balance (mobile, points, youzan_points_base) "
        "VALUES (?, ?, ?)",
        (MOBILE, 500, 500),
    )
    await db.commit()
    client = RecordingYouzanClient(
        {"gw_err_resp": {"err_code": 4005, "err_msg": "非法的API"}}
    )
    service = MemberLoyaltyImportService(db, client, tenant_id="yunxi")

    stats = await service.import_one(MOBILE, customer_id="cust-1", should_apply=True)

    assert stats["points_total"] == 0
    assert stats["errors"]
    rows = await db.execute_fetchall(
        "SELECT points, youzan_points_base FROM member_balance WHERE mobile = ?",
        (MOBILE,),
    )
    assert int(rows[0]["points"]) == 500
    assert int(rows[0]["youzan_points_base"]) == 500
