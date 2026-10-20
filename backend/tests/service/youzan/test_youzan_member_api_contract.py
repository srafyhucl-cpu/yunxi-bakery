"""有赞券/会员卡 API 契约测试。

锁死 2026-10-20 生产只读实测的契约事实（证据：有赞开放平台 API 目录 +
店铺 131707202 真实响应，脱敏见任务报告）：

1. **买家券列表**用 `youzan.ump.promocard.buyer.search` / `promocode.buyer.search`
   3.0.0；旧常量 `youzan.ump.coupon.user.coupons` 在有赞 API 目录中并不存在，
   任何版本都被网关以 4005「非法的API」拒绝，调用结果恒为空列表 → 漏券；
2. 买家券必须按 `VALID`/`USED`/`INVALID` 三种状态分别查询（返回集互相重叠，
   需按券 ID 去重），响应 `data` 直接是**数组**；
3. **券模板详情** `youzan.ump.coupon.detail.get` 3.0.0 的请求参数是 `id`
   （不是 `coupon_group_id`），传错会被判 161201012「id不能为null」；
4. **会员卡列表** `youzan.scrm.customer.card.list` 3.0.0 的分页参数是 `page`
   （不是 `page_no`/`page_size`），列表在响应 `items`；
5. 网关级错误必须抛出：静默返回空列表会把「接口被拒」误判成「客户没有券」。
"""

import aiosqlite
import pytest

from app.config import settings
from app.exceptions import APIError
from app.service.member_loyalty import MemberLoyaltyImportService
from app.service.youzan.member_api import (
    COUPON_CODE_LIST_API_NAME,
    COUPON_CODE_LIST_API_VERSION,
    COUPON_GROUP_DETAIL_API_NAME,
    COUPON_GROUP_DETAIL_API_VERSION,
    COUPON_LIST_API_NAME,
    COUPON_LIST_API_VERSION,
    COUPON_STATUS_INVALID,
    COUPON_STATUS_USED,
    COUPON_STATUS_VALID,
    MEMBER_CARD_LIST_API_NAME,
    MEMBER_CARD_LIST_API_VERSION,
    POINTS_QUERY_API_NAME,
    YouzanMemberApi,
)

MOBILE = "13600004015"
# 店铺 32035241「20元优惠卷」的真实券模板响应（脱敏后的字段集）。
COUPON_DETAIL = {
    "id": 32035241,
    "kdt_id": 131707202,
    "group_type": 7,
    "title": "20元优惠卷",
    "preferential_type": 1,
    "denominations": 2000,
    "condition": 5000,
    "discount": 0,
    "date_type": 2,
    "fixed_term": 30,
    "valid_start_time": 1727340981000,
    "valid_end_time": 4102416000000,
    "range_type": "all",
    "total_take": 236,
    "total_used": 219,
}


class RecordingYouzanClient:
    """按 API 名返回真实响应形状的假客户端，并记录每次调用。"""

    def __init__(
        self,
        *,
        points: dict | None = None,
        coupon_items: dict[str, list[dict]] | None = None,
        coupon_detail: dict | None = None,
        cards: list[dict] | None = None,
        gateway_error: dict | None = None,
    ) -> None:
        self._points = points if points is not None else {"point": 100}
        self._coupon_items = coupon_items or {}
        self._coupon_detail = coupon_detail if coupon_detail is not None else {}
        self._cards = cards if cards is not None else []
        self._gateway_error = gateway_error or {}
        self.calls: list[tuple[str, str, dict]] = []

    async def call_api(self, api_name: str, version: str, params: dict) -> dict:
        self.calls.append((api_name, version, params))
        if self._gateway_error:
            return {"gw_err_resp": dict(self._gateway_error)}
        if api_name == POINTS_QUERY_API_NAME:
            return {"code": 200, "success": True, "data": dict(self._points)}
        if api_name == COUPON_LIST_API_NAME:
            status = str(params.get("status", ""))
            return {
                "code": 200,
                "success": True,
                "data": self._coupon_items.get(status, []),
            }
        if api_name == COUPON_CODE_LIST_API_NAME:
            return {"code": 200, "success": True, "data": []}
        if api_name == COUPON_GROUP_DETAIL_API_NAME:
            return {"code": 200, "success": True, "data": dict(self._coupon_detail)}
        if api_name == MEMBER_CARD_LIST_API_NAME:
            return {
                "code": 200,
                "success": True,
                "data": {
                    "total": len(self._cards),
                    "page": 1,
                    "page_size": 30,
                    "items": list(self._cards),
                },
            }
        return {"code": 200, "success": True, "data": {}}


@pytest.mark.asyncio
async def test_coupon_list_uses_promocard_buyer_search_not_removed_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """买家券列表必须打 promocard/promocode 3.0.0，且按三种状态分别查询。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = RecordingYouzanClient(
        coupon_items={
            COUPON_STATUS_VALID: [
                {
                    "id": 68630192334,
                    "coupon_group_id": 32035320,
                    "preferential_type": 5,
                    "value": 0,
                    "is_used": 0,
                    "take_at": 1789644144000,
                    "valid_start_at": 1789574400000,
                    "expire_at": 1790179199000,
                }
            ],
            COUPON_STATUS_USED: [
                {
                    "id": 40715221865,
                    "coupon_group_id": 32035320,
                    "preferential_type": 5,
                    "value": 0,
                    "used_value": 300,
                    "is_used": 1,
                    "take_at": 1789643686000,
                    "used_in_order_no": "E20260917191700092700057",
                }
            ],
            COUPON_STATUS_INVALID: [
                {
                    "id": 40715221865,
                    "coupon_group_id": 32035320,
                    "is_used": 1,
                },
                {
                    "id": 67049193822,
                    "coupon_group_id": 32035320,
                    "is_used": 0,
                },
            ],
        }
    )

    coupons = await YouzanMemberApi(client).list_customer_coupons(MOBILE)

    api_names = {call[0] for call in client.calls}
    assert api_names == {COUPON_LIST_API_NAME, COUPON_CODE_LIST_API_NAME}
    assert "youzan.ump.coupon.user.coupons" not in api_names
    assert COUPON_LIST_API_VERSION == "3.0.0"
    assert COUPON_CODE_LIST_API_VERSION == "3.0.0"
    assert {call[1] for call in client.calls} == {"3.0.0"}
    # 三种状态都必须查，且请求体带 status 与手机号
    statuses = {
        call[2]["status"] for call in client.calls if call[0] == COUPON_LIST_API_NAME
    }
    assert statuses == {COUPON_STATUS_VALID, COUPON_STATUS_USED, COUPON_STATUS_INVALID}
    for _api, _version, params in client.calls:
        assert params["mobile"] == MOBILE
        assert "page_no" not in params
        assert "page_size" not in params

    # 按券 ID 去重：已失效且未使用的过期券不落库
    ids = [coupon["id"] for coupon in coupons]
    assert ids == [68630192334, 40715221865]
    assert coupons[0]["youzan_coupon_status"] == COUPON_STATUS_VALID
    assert coupons[1]["youzan_coupon_status"] == COUPON_STATUS_USED


@pytest.mark.asyncio
async def test_coupon_list_keeps_used_coupon_from_invalid_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已使用券即便只在 INVALID 返回集里出现，也必须保留（已核销事实）。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = RecordingYouzanClient(
        coupon_items={
            COUPON_STATUS_INVALID: [
                {"id": 39128113930, "coupon_group_id": 32035320, "is_used": 1}
            ]
        }
    )

    coupons = await YouzanMemberApi(client).list_customer_coupons(MOBILE)

    assert [coupon["id"] for coupon in coupons] == [39128113930]
    assert coupons[0]["youzan_coupon_status"] == COUPON_STATUS_INVALID


@pytest.mark.asyncio
async def test_coupon_group_detail_uses_id_param(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """券模板详情的请求参数必须是 `id`（传 coupon_group_id 恒空模板）。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = RecordingYouzanClient(coupon_detail=COUPON_DETAIL)

    detail = await YouzanMemberApi(client).get_coupon_group_detail("32035241")

    assert len(client.calls) == 1
    api_name, version, params = client.calls[0]
    assert api_name == COUPON_GROUP_DETAIL_API_NAME
    assert version == COUPON_GROUP_DETAIL_API_VERSION == "3.0.0"
    assert params["id"] == "32035241"
    assert "coupon_group_id" not in params
    # 响应是扁平 CouponGroup，模板字段必须原样透出
    assert detail["title"] == "20元优惠卷"
    assert detail["denominations"] == 2000
    assert detail["condition"] == 5000


@pytest.mark.asyncio
async def test_member_card_list_uses_page_param_and_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """会员卡列表必须用 `page` 分页，列表在响应 `items`。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = RecordingYouzanClient(
        cards=[
            {"card_no": "G1", "card_alias": "金卡", "card_start_time": 1727341443000}
        ]
    )

    cards = await YouzanMemberApi(client).list_customer_cards(MOBILE)

    assert len(client.calls) == 1
    api_name, version, params = client.calls[0]
    assert api_name == MEMBER_CARD_LIST_API_NAME
    assert version == MEMBER_CARD_LIST_API_VERSION == "3.0.0"
    assert params["page"] == 1
    assert params["mobile"] == MOBILE
    assert "page_no" not in params
    assert "page_size" not in params
    assert cards == [
        {"card_no": "G1", "card_alias": "金卡", "card_start_time": 1727341443000}
    ]


@pytest.mark.asyncio
async def test_gateway_error_must_not_be_treated_as_empty_coupon_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """网关 4005「非法的API」必须抛出，不能静默返回空列表（漏券）。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = RecordingYouzanClient(
        gateway_error={"err_code": 4005, "err_msg": "非法的API"}
    )

    with pytest.raises(APIError):
        await YouzanMemberApi(client).list_customer_coupons(MOBILE)

    with pytest.raises(APIError):
        await YouzanMemberApi(client).list_customer_cards(MOBILE)


@pytest.mark.asyncio
async def test_gateway_error_on_coupon_detail_returns_empty_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """券模板反查被网关拒绝时不抛异常（Webhook 路径不能因此中断）。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = RecordingYouzanClient(
        gateway_error={"err_code": 4005, "err_msg": "非法的API"}
    )

    detail = await YouzanMemberApi(client).get_coupon_group_detail("32035320")

    assert detail == {}


@pytest.mark.asyncio
async def test_import_maps_youzan_coupon_into_local_ledger(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """全量导入必须把有赞买家券写成可用的本地券行。

    落库口径（2026-10-20 生产实测的响应形状）：
    - 状态：上游 VALID/USED → 本地 TAKE/CONSUME（本地引擎只认本地词表）；
    - 面额：券模板 `denominations`（单位分）；
    - 有效期：券自身 `valid_start_at` / `expire_at`（毫秒）。
    """
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = RecordingYouzanClient(
        coupon_items={
            COUPON_STATUS_VALID: [
                {
                    "id": 68630192334,
                    "coupon_group_id": 32035241,
                    "preferential_type": 1,
                    "value": 2000,
                    "is_used": 0,
                    "take_at": 1789644144000,
                    "valid_start_at": 1789574400000,
                    "expire_at": 1790179199000,
                }
            ]
        },
        coupon_detail=COUPON_DETAIL,
    )
    service = MemberLoyaltyImportService(db, client, tenant_id="yunxi")

    stats = await service.import_one(MOBILE, customer_id="cust-1", should_apply=True)

    assert stats["errors"] == []
    assert stats["coupons"] == 1
    rows = await db.execute_fetchall(
        "SELECT coupon_id, status, title, value_fen, template_id, valid_from, "
        "valid_until, source, occurred_at FROM coupon_inventory"
    )
    assert len(rows) == 1
    assert rows[0]["coupon_id"] == "68630192334"
    assert rows[0]["status"] == "TAKE"
    assert rows[0]["title"] == "20元优惠卷"
    assert rows[0]["value_fen"] == 2000
    assert rows[0]["template_id"] == "32035241"
    assert rows[0]["valid_from"] == "2026-09-17"
    assert rows[0]["valid_until"] == "2026-09-23"
    assert rows[0]["source"] == "import"
    assert rows[0]["occurred_at"] == "2026-09-17 19:22:24"

    # 券模板必须落库，抵扣金额才有依据
    templates = await db.execute_fetchall(
        "SELECT id, name, coupon_type, threshold_fen, value_fen FROM coupon_templates"
    )
    assert len(templates) == 1
    assert templates[0]["id"] == "32035241"
    assert templates[0]["coupon_type"] == "FULL_REDUCTION"
    assert templates[0]["value_fen"] == 2000
    assert templates[0]["threshold_fen"] == 5000


@pytest.mark.asyncio
async def test_import_used_coupon_is_recorded_as_consume(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """已使用券必须落成 CONSUME（已核销事实），不得当成可用券。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)
    client = RecordingYouzanClient(
        coupon_items={
            COUPON_STATUS_USED: [
                {
                    "id": 40715221865,
                    "coupon_group_id": 32035241,
                    "value": 2000,
                    "used_value": 2000,
                    "is_used": 1,
                    "take_at": 1789643686000,
                    "used_in_order_no": "E20260917191700092700057",
                }
            ]
        },
        coupon_detail=COUPON_DETAIL,
    )
    service = MemberLoyaltyImportService(db, client, tenant_id="yunxi")

    stats = await service.import_one(MOBILE, customer_id="cust-1", should_apply=True)

    assert stats["errors"] == []
    rows = await db.execute_fetchall(
        "SELECT status, order_no FROM coupon_inventory WHERE coupon_id = ?",
        ("40715221865",),
    )
    assert len(rows) == 1
    assert rows[0]["status"] == "CONSUME"
    assert rows[0]["order_no"] == "E20260917191700092700057"


@pytest.mark.asyncio
async def test_import_card_failure_does_not_block_coupon_collect(
    db: aiosqlite.Connection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """会员卡接口失败不得让券整段漏采（三类账务互不连坐）。"""
    monkeypatch.setattr(settings, "YOUZAN_MOCK_MODE", False)

    class CardFailingClient(RecordingYouzanClient):
        async def call_api(self, api_name: str, version: str, params: dict) -> dict:
            if api_name == MEMBER_CARD_LIST_API_NAME:
                raise APIError("有赞会员卡接口异常")
            return await super().call_api(api_name, version, params)

    client = CardFailingClient(
        coupon_items={
            COUPON_STATUS_VALID: [
                {
                    "id": 68630192334,
                    "coupon_group_id": 32035241,
                    "value": 2000,
                    "is_used": 0,
                }
            ]
        },
        coupon_detail=COUPON_DETAIL,
    )
    service = MemberLoyaltyImportService(db, client, tenant_id="yunxi")

    stats = await service.import_one(MOBILE, customer_id="cust-1", should_apply=True)

    assert stats["coupons"] == 1
    assert stats["cards"] == 0
    assert stats["errors"]
    rows = await db.execute_fetchall("SELECT coupon_id FROM coupon_inventory")
    assert len(rows) == 1
