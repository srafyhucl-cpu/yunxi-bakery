from __future__ import annotations

from typing import Any

from app.models.employee_agent import OrderQueryKind, OrderQueryPlan
from app.service.wecom.intelligent_bot_order_lookup import WeComOrderLookupService


class _FakeCustomerHistoryRepo:
    def __init__(self) -> None:
        self.queried_plans: list[OrderQueryPlan] = []
        self.summarized_plans: list[OrderQueryPlan] = []

    async def get_by_order_no(self, order_no: str) -> dict[str, Any] | None:
        if order_no == "E202600000000":
            return _youzan_order(order_no, "buyer_same")
        return None

    async def summarize_orders(self, plan: OrderQueryPlan) -> dict[str, Any]:
        self.summarized_plans.append(plan)
        return {"total_count": 2, "total_amount_fen": 46000, "status_counts": {}}

    async def query_orders(self, plan: OrderQueryPlan) -> list[dict[str, Any]]:
        self.queried_plans.append(plan)
        if plan.buyer_id == "buyer_same":
            return [
                _youzan_order("E202600000000", "buyer_same"),
                _youzan_order("E202600000001", "buyer_same"),
            ]
        return []


async def test_answer_agent_query_lists_customer_history_by_buyer_id() -> None:
    repo = _FakeCustomerHistoryRepo()
    service = WeComOrderLookupService(youzan_order_repo=repo)

    result = await service.answer_agent_query(
        "E202600000000 这个客户还买过什么",
        OrderQueryPlan(kind=OrderQueryKind.LIST),
    )

    assert result.ok is True
    assert "该客户历史订单：找到 2 单" in result.summary
    assert "buyer_same" not in result.summary
    assert repo.queried_plans[0].buyer_id == "buyer_same"
    assert repo.summarized_plans[0].buyer_id == "buyer_same"


async def test_answer_agent_query_rejects_unknown_customer_history_order_no() -> None:
    repo = _FakeCustomerHistoryRepo()
    service = WeComOrderLookupService(youzan_order_repo=repo)

    result = await service.answer_agent_query(
        "E202699999999 这个客户还买过什么",
        OrderQueryPlan(kind=OrderQueryKind.LIST),
    )

    assert result.ok is False
    assert "未找到该交易号" in result.summary
    assert "buyer_same" not in result.summary


def _youzan_order(order_no: str, buyer_id: str) -> dict[str, Any]:
    return {
        "order_no": order_no,
        "buyer_id": buyer_id,
        "status": "WAIT_SELLER_SEND_GOODS",
        "amount_fen": 23000,
        "logistics_no": "",
        "logistics_status": "",
        "product_titles": "杏好有你 x 1",
        "total_quantity": 1,
        "pay_time": "2026-07-05 10:00:00",
        "delivery_province": "上海市",
        "delivery_city": "上海市",
        "delivery_district": "浦东新区",
        "delivery_time": "2026-07-06 18:00:00",
    }
