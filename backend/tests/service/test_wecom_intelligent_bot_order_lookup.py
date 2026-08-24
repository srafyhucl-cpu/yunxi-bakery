from __future__ import annotations

import json
from typing import Any

import pytest

from app.models.employee_agent import OrderQueryKind, OrderQueryPlan
from app.service.wecom import intelligent_bot_order_lookup as order_lookup_module
from app.service.wecom.intelligent_bot_order_lookup import WeComOrderLookupService


class _FakeYouzanOrderRepo:
    def __init__(self) -> None:
        self.searches: list[tuple[str, int]] = []
        self.recent_limits: list[int] = []
        self.summarized_plans: list[OrderQueryPlan] = []
        self.queried_plans: list[OrderQueryPlan] = []

    async def get_by_order_no(self, order_no: str) -> dict[str, Any] | None:
        if order_no == "E202600000000":
            return _youzan_order(order_no)
        return None

    async def search_orders(self, keyword: str, limit: int = 5) -> list[dict[str, Any]]:
        self.searches.append((keyword, limit))
        if keyword == "草莓":
            return [_youzan_order("E202600000001")]
        return []

    async def list_recent_orders(self, limit: int = 5) -> list[dict[str, Any]]:
        self.recent_limits.append(limit)
        return [_youzan_order("E202600000002")]

    async def summarize_orders(self, plan: OrderQueryPlan) -> dict[str, Any]:
        self.summarized_plans.append(plan)
        if plan.needs_refund:
            return {"total_count": 1, "total_amount_fen": 8800, "status_counts": {}}
        if plan.statuses:
            return {"total_count": 2, "total_amount_fen": 43600, "status_counts": {}}
        return {
            "total_count": 4,
            "total_amount_fen": 78800,
            "status_counts": {"WAIT_SELLER_SEND_GOODS": 2},
        }

    async def query_orders(self, plan: OrderQueryPlan) -> list[dict[str, Any]]:
        self.queried_plans.append(plan)
        if plan.needs_fulfillment_risk:
            return [_youzan_order("E202600000011")]
        if plan.needs_missing_logistics:
            return [_youzan_order("E202600000012")]
        return [_youzan_order("E202600000013"), _youzan_order("E202600000014")]


class _EmptyYouzanOrderRepo(_FakeYouzanOrderRepo):
    async def summarize_orders(self, plan: OrderQueryPlan) -> dict[str, Any]:
        self.summarized_plans.append(plan)
        return {"total_count": 0, "total_amount_fen": 0, "status_counts": {}}

    async def query_orders(self, plan: OrderQueryPlan) -> list[dict[str, Any]]:
        self.queried_plans.append(plan)
        return []


class _FakePlatformOrderService:
    async def list_admin_orders(self, *, page: int = 1, keyword: str = "") -> dict:
        return {
            "items": [
                {
                    "id": "ord_001",
                    "status": "pending",
                    "paymentStatus": "unpaid",
                    "itemTitle": "草莓蛋糕",
                    "itemCount": 1,
                    "totalFen": 26800,
                    "receiverName": "张三",
                    "receiverPhone": "13812345678",
                    "expectTime": "2026-07-03 18:00",
                    "createdAt": "2026-07-02 12:00:00",
                }
            ],
            "total": 1,
        }


async def test_lookup_orders_searches_youzan_orders_first() -> None:
    repo = _FakeYouzanOrderRepo()
    service = WeComOrderLookupService(
        order_service=_FakePlatformOrderService(),
        youzan_order_repo=repo,
    )

    payload = await service.lookup_orders("草莓", 3)

    assert repo.searches == [("草莓", 3)]
    assert payload["ok"] is True
    assert payload["orders"][0]["source"] == "youzan_orders"
    assert payload["orders"][0]["orderNo"] == "E202600000001"
    assert "草莓蛋糕 x 1 x 1" not in payload["ordersText"]
    assert "13812345678" not in json.dumps(payload, ensure_ascii=False)


async def test_lookup_orders_removes_generic_order_words_for_product_search() -> None:
    repo = _FakeYouzanOrderRepo()
    service = WeComOrderLookupService(youzan_order_repo=repo)

    payload = await service.lookup_orders("帮我查一下草莓订单", 3)

    assert repo.searches == [("草莓", 3)]
    assert payload["orders"][0]["orderNo"] == "E202600000001"


async def test_lookup_orders_supports_recent_query() -> None:
    repo = _FakeYouzanOrderRepo()
    service = WeComOrderLookupService(youzan_order_repo=repo)

    payload = await service.lookup_orders("查最近订单", 2)

    assert repo.recent_limits == [2]
    assert payload["orders"][0]["orderNo"] == "E202600000002"


async def test_lookup_orders_falls_back_to_platform_orders() -> None:
    service = WeComOrderLookupService(
        order_service=_FakePlatformOrderService(),
        youzan_order_repo=_FakeYouzanOrderRepo(),
    )

    payload = await service.lookup_orders("张三", 5)

    assert payload["orders"][0]["source"] == "platform_orders"
    assert payload["orders"][0]["receiverPhoneMasked"] == "138****5678"


async def test_lookup_orders_calls_live_order_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, Any] = {}

    async def fake_get_order_info(
        knowledge_retriever: Any,
        order_no: str,
        youzan_client: Any = None,
    ) -> str:
        called["order_no"] = order_no
        called["youzan_client"] = youzan_client
        return json.dumps(
            {
                "order_no": order_no,
                "status": "TRADE_PAID",
                "amount_yuan": 268,
                "product_titles": "草莓蛋糕 x 1",
                "delivery_city": "上海市",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(order_lookup_module, "get_order_info", fake_get_order_info)
    service = WeComOrderLookupService(
        knowledge_retriever=object(),
        youzan_client="youzan-client",
    )

    payload = await service.lookup_orders("查 E202600000003", 5)

    assert called == {
        "order_no": "E202600000003",
        "youzan_client": "youzan-client",
    }
    assert payload["orders"][0]["orderNo"] == "E202600000003"
    assert "草莓蛋糕" in payload["ordersText"]


async def test_answer_agent_query_builds_order_action_items() -> None:
    repo = _FakeYouzanOrderRepo()
    service = WeComOrderLookupService(youzan_order_repo=repo)

    result = await service.answer_agent_query(
        "今天有什么要盯的",
        OrderQueryPlan(
            kind=OrderQueryKind.ACTION_ITEMS,
            date_from="2026-07-03",
            date_to="2026-07-03",
        ),
    )

    assert result.ok is True
    assert "今天 4 单" in result.summary
    assert "待处理 2 单" in result.summary
    assert "履约风险 1 单" in result.summary
    assert "无物流 1 单" in result.summary
    assert "E202600000011" not in result.summary
    assert "000011" in result.summary
    assert any(plan.needs_refund for plan in repo.summarized_plans)
    assert any(plan.needs_fulfillment_risk for plan in repo.queried_plans)
    assert any(plan.needs_missing_logistics for plan in repo.queried_plans)


async def test_answer_agent_query_adds_fulfillment_pressure_label() -> None:
    repo = _FakeYouzanOrderRepo()
    service = WeComOrderLookupService(youzan_order_repo=repo)

    result = await service.answer_agent_query(
        "今天发货压力大不大",
        OrderQueryPlan(
            kind=OrderQueryKind.LIST,
            date_from="2026-07-03",
            date_to="2026-07-03",
            statuses=("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS"),
            needs_fulfillment_risk=True,
        ),
    )

    assert "发货压力：偏高" in result.summary
    assert "待处理 2 单" in result.summary
    assert "履约风险 1 单" in result.summary


async def test_answer_agent_query_empty_list_keeps_query_scope() -> None:
    repo = _EmptyYouzanOrderRepo()
    service = WeComOrderLookupService(youzan_order_repo=repo)

    result = await service.answer_agent_query(
        "晚上还有哪些待处理订单",
        OrderQueryPlan(
            kind=OrderQueryKind.LIST,
            date_from="2026-07-04",
            date_to="2026-07-04",
            date_field="delivery_time",
            statuses=("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS"),
            delivery_time_start="18:00",
            delivery_time_end="23:59",
        ),
    )

    assert "没有查到约送日期 2026-07-04" in result.summary
    assert "约送时间 18:00-23:59" in result.summary
    assert "待处理" in result.summary
    assert "换商品名" not in result.next_action
    assert "当前约送口径下暂无待处理订单" in result.next_action


async def test_lookup_orders_calls_live_logistics_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, Any] = {}

    async def fake_get_logistics_info(
        knowledge_retriever: Any,
        order_no: str,
        youzan_client: Any = None,
    ) -> str:
        called["order_no"] = order_no
        return json.dumps(
            {
                "order_no": order_no,
                "express_name": "顺丰",
                "express_id": "SF123",
                "steps": ["已送达"],
                "message": "查询成功",
            },
            ensure_ascii=False,
        )

    monkeypatch.setattr(
        order_lookup_module,
        "get_logistics_info",
        fake_get_logistics_info,
    )
    service = WeComOrderLookupService(knowledge_retriever=object())

    payload = await service.lookup_orders("E202600000004 物流到哪了", 5)

    assert called == {"order_no": "E202600000004"}
    assert payload["orders"][0]["logisticsNo"] == "SF123"
    assert "已送达" in payload["ordersText"]


def _youzan_order(order_no: str) -> dict[str, Any]:
    return {
        "order_no": order_no,
        "buyer_id": "buyer_13812345678",
        "status": "TRADE_PAID",
        "amount_fen": 26800,
        "logistics_no": "",
        "logistics_status": "",
        "product_titles": "草莓蛋糕 x 1",
        "total_quantity": 1,
        "pay_time": "2026-07-03 12:00:00",
        "delivery_province": "上海市",
        "delivery_city": "上海市",
        "delivery_district": "浦东新区",
        "delivery_time": "2026-07-03 18:00",
        "outer_user_id": "outer_13812345678",
    }
