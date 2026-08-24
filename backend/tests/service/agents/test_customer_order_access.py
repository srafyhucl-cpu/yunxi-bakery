from __future__ import annotations

import json
from typing import Any

import pytest

from app.models.session import Session
from app.service.agents.tools.customer import (
    CustomerToolContext,
    resolve_customer_order_identity,
)
from app.service.llm.function_tool_order import get_order_info, get_logistics_info


class _ScopedOrderRepo:
    def __init__(self, local_order: dict[str, Any] | None = None) -> None:
        self.local_order = local_order
        self.scoped_calls: list[tuple[str, str | None, str | None]] = []
        self.unscoped_calls = 0
        self.upserted_orders: list[Any] = []

    async def get_by_order_no_for_identity(
        self,
        order_no: str,
        *,
        buyer_id: str | None,
        outer_user_id: str | None,
    ) -> dict[str, Any] | None:
        self.scoped_calls.append((order_no, buyer_id, outer_user_id))
        return self.local_order

    async def get_by_order_no(self, order_no: str) -> dict[str, Any] | None:
        self.unscoped_calls += 1
        return self.local_order

    async def upsert_order(self, order: Any) -> None:
        self.upserted_orders.append(order)


class _FakeYouzanClient:
    def __init__(self, raw_order: dict[str, Any] | None = None) -> None:
        self.raw_order = raw_order
        self.order_calls: list[str] = []
        self.logistics_calls: list[str] = []

    async def get_order(self, order_no: str) -> dict[str, Any]:
        self.order_calls.append(order_no)
        return self.raw_order or {}

    async def get_logistics(self, order_no: str) -> dict[str, Any]:
        self.logistics_calls.append(order_no)
        return {
            "data": {
                "express_id": "SF123",
                "express_name": "顺丰",
                "transit_step_infos": [
                    {"status_time": "18:00", "status_desc": "已送达"}
                ],
            }
        }


def test_resolve_customer_order_identity_uses_only_trusted_session_fields() -> None:
    youzan_identity = resolve_customer_order_identity(
        Session(
            id="session-youzan",
            channel="youzan",
            user_id="buyer-1",
            extra_info=json.dumps({"outer_user_id": "outer-1"}),
        )
    )
    unsupported_identity = resolve_customer_order_identity(
        Session(
            id="session-wecom",
            channel="wecom_1on1",
            user_id="external-1",
        )
    )
    missing_identity = resolve_customer_order_identity(None)

    assert youzan_identity is not None
    assert youzan_identity.buyer_id == "buyer-1"
    assert youzan_identity.outer_user_id == "outer-1"
    assert unsupported_identity is None
    assert missing_identity is None


@pytest.mark.asyncio
async def test_customer_order_tool_reads_only_same_buyer_order() -> None:
    from app.service.agents.tools.registry import build_tools

    order_repo = _ScopedOrderRepo(
        {
            "order_no": "E202607050001",
            "buyer_id": "buyer-1",
            "status": "TRADE_SUCCESS",
            "amount_fen": 18800,
            "product_titles": "草莓蛋糕",
            "logistics_no": "SF123",
            "logistics_status": "已送达",
        }
    )
    tools = {
        tool.name: tool
        for tool in build_tools(
            "customer",
            customer_context=CustomerToolContext(
                session=Session(
                    id="session-1",
                    channel="youzan",
                    user_id="buyer-1",
                ),
                knowledge_retriever=object(),
                order_repo=order_repo,
            ),
        )
    }

    result = json.loads(
        await tools["get_order_info"].ainvoke({"order_no": "E202607050001"})
    )

    assert result["amount_yuan"] == 188
    assert result["product_titles"] == "草莓蛋糕"
    assert order_repo.unscoped_calls == 0
    assert order_repo.scoped_calls == [("E202607050001", "buyer-1", None)]


@pytest.mark.asyncio
async def test_customer_order_tool_denies_different_buyer_without_leaking_details() -> (
    None
):
    from app.service.agents.tools.registry import build_tools

    order_repo = _ScopedOrderRepo(None)
    tools = {
        tool.name: tool
        for tool in build_tools(
            "customer",
            customer_context=CustomerToolContext(
                session=Session(
                    id="session-2",
                    channel="youzan",
                    user_id="buyer-2",
                ),
                knowledge_retriever=object(),
                order_repo=order_repo,
            ),
        )
    }

    result = json.loads(
        await tools["get_order_info"].ainvoke({"order_no": "E202607050001"})
    )
    result_text = json.dumps(result, ensure_ascii=False)

    assert result["message"] == "无法确认订单归属，请转人工客服"
    assert "188" not in result_text
    assert "草莓蛋糕" not in result_text
    assert "浦东新区" not in result_text
    assert "SF123" not in result_text
    assert order_repo.unscoped_calls == 0


@pytest.mark.asyncio
async def test_missing_session_denies_order_access() -> None:
    from app.service.agents.tools.registry import build_tools

    tools = {
        tool.name: tool
        for tool in build_tools(
            "customer",
            customer_context=CustomerToolContext(
                session=None,
                knowledge_retriever=object(),
                order_repo=_ScopedOrderRepo(),
            ),
        )
    }

    result = json.loads(
        await tools["get_order_info"].ainvoke({"order_no": "E202607050001"})
    )

    assert result["message"] == "无法确认订单归属，请转人工客服"


@pytest.mark.asyncio
async def test_customer_logistics_uses_the_same_ownership_filter() -> None:
    order_repo = _ScopedOrderRepo(None)
    youzan_client = _FakeYouzanClient()

    result = json.loads(
        await get_logistics_info(
            object(),
            "E202607050001",
            youzan_client=youzan_client,
            order_repo=order_repo,
            buyer_id="buyer-2",
        )
    )

    assert result["message"] == "无法确认订单归属，请转人工客服"
    assert youzan_client.logistics_calls == []
    assert order_repo.unscoped_calls == 0


@pytest.mark.asyncio
async def test_live_youzan_order_with_mismatched_identity_is_denied_and_not_cached() -> (
    None
):
    order_repo = _ScopedOrderRepo(None)
    youzan_client = _FakeYouzanClient(
        {
            "data": {
                "full_order_info": {
                    "order_info": {
                        "status": "TRADE_SUCCESS",
                        "created": "2026-07-05 10:00:00",
                        "update_time": "2026-07-05 10:00:00",
                    },
                    "pay_info": {"payment": "188.00"},
                    "buyer_info": {
                        "buyer_id": "buyer-other",
                        "outer_user_id": "outer-other",
                    },
                    "address_info": {"delivery_district": "浦东新区"},
                    "orders": [{"title": "草莓蛋糕", "num": 1}],
                }
            }
        }
    )

    result = json.loads(
        await get_order_info(
            object(),
            "E202607050001",
            youzan_client=youzan_client,
            order_repo=order_repo,
            buyer_id="buyer-same",
        )
    )

    assert result["message"] == "无法确认订单归属，请转人工客服"
    assert "188" not in json.dumps(result, ensure_ascii=False)
    assert "草莓蛋糕" not in json.dumps(result, ensure_ascii=False)
    assert "浦东新区" not in json.dumps(result, ensure_ascii=False)
    assert order_repo.upserted_orders == []
