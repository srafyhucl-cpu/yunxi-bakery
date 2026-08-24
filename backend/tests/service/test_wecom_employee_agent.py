from __future__ import annotations

from datetime import date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

from app.models.employee_agent import (
    AgentIntent,
    AgentPlan,
    AnswerStyle,
    OrderQueryKind,
    OrderQueryPlan,
    ToolResult,
)
from app.service.wecom import employee_agent_planner
from app.service.wecom.employee_agent_planner import EmployeeAgentPlanner
from app.service.wecom.employee_agent_service import EmployeeAgentService
from app.service.wecom.intelligent_bot_order_format import (
    build_order_list_tool_result,
    build_top_products_tool_result,
    employee_delivery_time_text,
)
from app.service.wecom.intelligent_bot_product_action import product_next_action


class _FakeOrderLookupService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    async def answer_agent_query(self, query: str, plan: Any) -> ToolResult:
        self.calls.append((query, plan))
        return ToolResult(
            ok=True,
            summary="今天共 2 单，待发货 1 单。",
            next_action="需要处理待发货订单。",
        )


class _FakeActionItemsOrderLookupService:
    async def answer_agent_query(self, query: str, plan: Any) -> ToolResult:
        return ToolResult(
            ok=True,
            summary=(
                "今天有什么要盯的：\n"
                "今天 1 单，合计 206.50 元；发货压力：偏高。\n"
                "待处理 1 单，履约风险 1 单，退款/售后 0 单，无物流 1 单。\n"
                "优先级 1：先处理快到约送时间的履约风险单\n"
                "1. 尾号 000001｜待发货｜巧克力樱桃炸弹 x 1｜206.50 元"
            ),
            next_action="先处理履约风险单，再按无物流、退款/售后顺序核对。",
        )


class _FakeMarkdownOrderLookupService:
    async def answer_agent_query(self, query: str, plan: Any) -> ToolResult:
        return ToolResult(
            ok=True,
            summary="**今日销量第一**：`巧克力樱桃炸弹`，共1单。",
        )


class _FakeFulfillmentRiskOrderLookupService:
    async def answer_agent_query(self, query: str, plan: Any) -> ToolResult:
        return ToolResult(
            ok=True,
            summary=(
                "哪些单快超时了：找到 2 单，按约送时间展示：\n"
                "1. 尾号 200101｜待收货｜水果盛宴 x 1｜313.00 元｜"
                "2026-06-06 10:00｜约送 2026-06-06 11:00｜暂无物流\n"
                "2. 尾号 200023｜待收货｜焦糖杏仁糯米船 x 1｜198.00 元｜"
                "2026-06-07 10:00｜约送 2026-06-07 11:00｜暂无物流"
            ),
            next_action="这些是履约风险单，请按约送时间从早到晚优先处理。",
        )


class _FakeOverdueFulfillmentRiskOrderLookupService:
    async def answer_agent_query(self, query: str, plan: Any) -> ToolResult:
        return ToolResult(
            ok=True,
            summary=(
                "哪些单快超时了：找到 2 单，按约送时间展示：\n"
                "1. 尾号 200101｜待收货｜水果盛宴 x 1｜313.00 元｜"
                "2026-06-06 10:00｜约送 2026-06-06 11:00（已过约送时间）｜暂无物流\n"
                "2. 尾号 200023｜待收货｜焦糖杏仁糯米船 x 1｜198.00 元｜"
                "2026-06-07 10:00｜约送 2026-06-07 11:00（已过约送时间）｜暂无物流"
            ),
            next_action="这些是履约风险单，请按已过约送时间和约送时间从早到晚优先处理。",
        )


class _FakeMissingLogisticsOrderLookupService:
    async def answer_agent_query(self, query: str, plan: Any) -> ToolResult:
        return ToolResult(
            ok=True,
            summary=(
                "还没物流的订单有哪些：找到 1 单，按最新订单展示：\n"
                "1. 尾号 000001｜待发货｜巧克力樱桃炸弹 x 1｜206.50 元｜"
                "2026-07-04 10:00｜约送 2026-07-04 16:00｜暂无物流"
            ),
            next_action="列表默认只展示订单尾号，排查时可用尾号继续追问。",
        )


class _FakePendingOrderListLookupService:
    async def answer_agent_query(self, query: str, plan: Any) -> ToolResult:
        return ToolResult(
            ok=True,
            summary=(
                "还有哪些没发货：找到 2 单，按最新订单展示：\n"
                "1. 尾号 300061｜待发货｜雾蓝奥利奥 x 1｜158.00 元｜"
                "2026-07-04 13:52:38｜未约送｜暂无物流\n"
                "2. 尾号 700059｜待发货｜杏好有你 x 1｜302.50 元｜"
                "2026-07-04 13:24:39｜约送 2026-07-06 11:00:00｜暂无物流"
            ),
            next_action="列表默认只展示订单尾号，排查时可用尾号继续追问。",
        )


class _FakeMissingLogisticsClosedRefundOrderLookupService:
    async def answer_agent_query(self, query: str, plan: Any) -> ToolResult:
        return ToolResult(
            ok=True,
            summary=(
                "哪些单子还没出物流：找到 5 单，按最新订单展示：\n"
                "1. 尾号 000077｜已关闭｜售后退款蛋糕 x 1｜88.00 元｜"
                "2026-07-04 09:00｜约送 2026-07-04 15:00｜暂无物流｜有退款/售后"
            ),
            next_action="先核对未出物流原因；已关闭或退款售后单单独标记，避免误催发货。",
        )


class _FakeTopProductsTieOrderLookupService:
    async def answer_agent_query(self, query: str, plan: Any) -> ToolResult:
        return ToolResult(
            ok=True,
            summary=(
                "今天卖爆的是哪个：按销量粗略排行如下：\n"
                "1. 巧克力樱桃炸弹：1 件，1 单，206.50 元\n"
                "2. 绿野仙踪蝴蝶款：1 件，1 单，273.50 元\n"
                "提示：当前销量并列且样本很少，还不能判断单一爆款。"
            ),
            next_action="如需备货判断，建议继续结合库存、履约压力和后续订单趋势。",
        )


class _FakeTopProductsOrderLookupService:
    async def answer_agent_query(self, query: str, plan: Any) -> ToolResult:
        return ToolResult(
            ok=True,
            summary=(
                "本周哪个商品卖得多：按销量粗略排行如下：\n"
                "1. 红豆碱水包、椰蓉碱水包：18 件，2 单，188.00 元\n"
                "2. 巧克力樱桃炸弹：6 件，6 单，1239.00 元"
            ),
            next_action="如需备货判断，建议继续结合库存和履约压力。",
        )


class _FakeBusinessToolService:
    def __init__(self) -> None:
        self.product_payloads: list[dict[str, Any]] = []

    async def lookup_orders(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "订单兜底"}

    async def lookup_products(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.product_payloads.append(payload)
        return {"ok": True, "result": "草莓蛋糕｜库存 6"}

    async def answer_knowledge(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": f"知识库回复：{payload.get('question')}。"}


class _FakeBusinessToolServiceWithKnowledgeMiss(_FakeBusinessToolService):
    async def lookup_products(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.product_payloads.append(payload)
        return {
            "ok": True,
            "result": "伯牙绝弦｜258.00元｜库存 72｜生日蛋糕",
            "products": [
                {
                    "title": "伯牙绝弦",
                    "priceFen": 25800,
                    "stock": 72,
                    "categoryName": "生日蛋糕",
                }
            ],
            "nextAction": "库存和价格以小程序商品数据为准；可按当前库存回复，特殊数量先人工核对。",
        }

    async def answer_knowledge(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "result": "未找到匹配知识。",
            "nextAction": "员工可复制建议回复；如知识缺失，请到后台知识库补充。",
        }


class _FakeBusinessToolServiceWithNoStock(_FakeBusinessToolService):
    async def lookup_products(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.product_payloads.append(payload)
        return {
            "ok": True,
            "result": "招牌牛奶吐司｜15.00元｜库存 0｜甜品和面包",
            "products": [
                {
                    "title": "招牌牛奶吐司",
                    "priceFen": 1500,
                    "stock": 0,
                    "categoryName": "甜品和面包",
                }
            ],
            "nextAction": "当前命中商品暂无可售库存，先不要承诺有货；可推荐同品类或相近价位替代款。",
        }


class _FakeBusinessToolServiceWithProductMiss(_FakeBusinessToolService):
    async def lookup_products(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.product_payloads.append(payload)
        return {
            "ok": True,
            "result": "未找到匹配商品",
            "products": [],
            "nextAction": "请换商品名、品类或关键词再查；不要把未命中结果当作缺货结论。",
        }


class _FakeOpsToolService:
    async def lookup_customer(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "找到 1 条地址/客户线索。"}

    async def summarize_group_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "result": f"群活动 {payload.get('campaignId')} 已汇总。",
        }

    async def list_pending_handoffs(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "当前待人工 1 个。"}


class _FakeStatusToolService:
    async def summarize_ops(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "系统状态 attention。"}

    async def summarize_integrations(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "同步失败 0 条。"}

    async def summarize_offline_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"ok": True, "result": "昨晚离线复盘已完成。"}


def _planner() -> EmployeeAgentPlanner:
    return EmployeeAgentPlanner(
        today_provider=lambda: date(2026, 7, 3),
        enable_llm=False,
    )


def _product(stock: int) -> dict[str, Any]:
    return {"title": "草莓蛋糕", "stock": stock}


async def test_planner_builds_today_order_summary_plan() -> None:
    plan = await _planner().plan("今天一共多少订单")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.SUMMARY
    assert plan.query_plan.date_from == "2026-07-03"
    assert plan.query_plan.date_to == "2026-07-03"


async def test_planner_builds_revenue_summary_plan() -> None:
    plan = await _planner().plan("今天营业额多少")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.SUMMARY
    assert plan.query_plan.date_from == "2026-07-03"
    assert plan.query_plan.date_to == "2026-07-03"
    assert plan.query_plan.keyword == ""


async def test_planner_builds_this_week_revenue_summary_plan() -> None:
    plan = await _planner().plan("本周销售额怎么样")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.SUMMARY
    assert plan.query_plan.date_from == "2026-06-29"
    assert plan.query_plan.date_to == "2026-07-03"
    assert plan.query_plan.keyword == ""


async def test_planner_builds_this_month_revenue_summary_plan() -> None:
    plan = await _planner().plan("本月销售额怎么样")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.SUMMARY
    assert plan.query_plan.date_from == "2026-07-01"
    assert plan.query_plan.date_to == "2026-07-03"
    assert plan.query_plan.keyword == ""


async def test_planner_builds_refund_order_summary_plan() -> None:
    plan = await _planner().plan("今天有退款订单吗")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.SUMMARY
    assert plan.query_plan.date_from == "2026-07-03"
    assert plan.query_plan.date_to == "2026-07-03"
    assert plan.query_plan.needs_refund is True
    assert plan.query_plan.keyword == ""


async def test_planner_builds_last_week_refund_summary_plan() -> None:
    plan = await _planner().plan("上周退款多少")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.SUMMARY
    assert plan.query_plan.date_from == "2026-06-22"
    assert plan.query_plan.date_to == "2026-06-28"
    assert plan.query_plan.needs_refund is True
    assert plan.query_plan.keyword == ""


async def test_planner_builds_fulfillment_risk_list_plan() -> None:
    plan = await _planner().plan("哪些单快超时了")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.LIST
    assert plan.query_plan.statuses == (
        "WAIT_SELLER_SEND_GOODS",
        "WAIT_BUYER_CONFIRM_GOODS",
    )
    assert plan.query_plan.needs_fulfillment_risk is True
    assert plan.query_plan.sort_by == "delivery_time"
    assert plan.query_plan.keyword == ""


async def test_planner_builds_order_action_items_plan() -> None:
    plan = await _planner().plan("今天有什么要盯的")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.ACTION_ITEMS
    assert plan.answer_style == AnswerStyle.ACTION_ITEMS
    assert plan.query_plan.date_from == "2026-07-03"
    assert plan.query_plan.date_to == "2026-07-03"
    assert plan.query_plan.keyword == ""


async def test_planner_keeps_refund_policy_as_knowledge() -> None:
    plan = await _planner().plan("退款规则是什么")

    assert plan.intent == AgentIntent.KNOWLEDGE_ANSWER
    assert plan.tools == ("knowledge_answer",)
    assert plan.query_plan is None


async def test_planner_builds_order_knowledge_multi_tool_plan() -> None:
    plan = await _planner().plan("还有哪些没发货，怎么跟客户说")

    assert plan.intent == AgentIntent.MULTI_TOOL
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.LIST
    assert plan.query_plan.statuses == ("WAIT_SELLER_SEND_GOODS",)
    assert plan.tools == ("order_dynamic_query", "knowledge_answer")


async def test_planner_builds_pending_order_list_plan() -> None:
    plan = await _planner().plan("还有哪些没发货")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.statuses == ("WAIT_SELLER_SEND_GOODS",)


async def test_planner_does_not_use_status_word_as_order_keyword() -> None:
    plan = await _planner().plan("今天待收货订单有哪些")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.statuses == ("WAIT_BUYER_CONFIRM_GOODS",)
    assert plan.query_plan.keyword == ""


async def test_planner_builds_evening_pending_order_window_plan() -> None:
    plan = await _planner().plan("晚上还有哪些待处理订单")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.LIST
    assert plan.query_plan.date_from == "2026-07-03"
    assert plan.query_plan.date_to == "2026-07-03"
    assert plan.query_plan.date_field == "delivery_time"
    assert plan.query_plan.statuses == (
        "WAIT_SELLER_SEND_GOODS",
        "WAIT_BUYER_CONFIRM_GOODS",
    )
    assert plan.query_plan.delivery_time_start == "18:00"
    assert plan.query_plan.delivery_time_end == "23:59"
    assert plan.query_plan.keyword == ""


async def test_planner_builds_tomorrow_pending_delivery_date_plan() -> None:
    plan = await _planner().plan("明天有哪些待处理订单")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.LIST
    assert plan.query_plan.date_from == "2026-07-04"
    assert plan.query_plan.date_to == "2026-07-04"
    assert plan.query_plan.date_field == "delivery_time"
    assert plan.query_plan.statuses == (
        "WAIT_SELLER_SEND_GOODS",
        "WAIT_BUYER_CONFIRM_GOODS",
    )
    assert plan.query_plan.keyword == ""


async def test_planner_builds_after_tomorrow_pending_delivery_date_plan() -> None:
    plan = await _planner().plan("后天有哪些待处理订单")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.LIST
    assert plan.query_plan.date_from == "2026-07-05"
    assert plan.query_plan.date_to == "2026-07-05"
    assert plan.query_plan.date_field == "delivery_time"
    assert plan.query_plan.statuses == (
        "WAIT_SELLER_SEND_GOODS",
        "WAIT_BUYER_CONFIRM_GOODS",
    )
    assert plan.query_plan.keyword == ""


async def test_planner_builds_weekend_pending_delivery_date_plan() -> None:
    plan = await _planner().plan("周末有哪些待处理订单")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.LIST
    assert plan.query_plan.date_from == "2026-07-04"
    assert plan.query_plan.date_to == "2026-07-05"
    assert plan.query_plan.date_field == "delivery_time"
    assert plan.query_plan.statuses == (
        "WAIT_SELLER_SEND_GOODS",
        "WAIT_BUYER_CONFIRM_GOODS",
    )
    assert plan.query_plan.keyword == ""


async def test_planner_builds_next_monday_pending_delivery_date_plan() -> None:
    plan = await _planner().plan("下周一有哪些待处理订单")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.LIST
    assert plan.query_plan.date_from == "2026-07-06"
    assert plan.query_plan.date_to == "2026-07-06"
    assert plan.query_plan.date_field == "delivery_time"
    assert plan.query_plan.statuses == (
        "WAIT_SELLER_SEND_GOODS",
        "WAIT_BUYER_CONFIRM_GOODS",
    )
    assert plan.query_plan.keyword == ""


async def test_planner_builds_product_order_multi_tool_plan() -> None:
    plan = await _planner().plan("椰椰凤梨今天卖了几单，库存还够吗")

    assert plan.intent == AgentIntent.MULTI_TOOL
    assert plan.query_plan is not None
    assert plan.query_plan.keyword == "椰椰凤梨"
    assert plan.tools == ("order_dynamic_query", "product_lookup")


async def test_planner_builds_top_products_plan() -> None:
    plan = await _planner().plan("今天哪个商品卖得多")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.TOP_PRODUCTS
    assert plan.query_plan.date_from == "2026-07-03"


async def test_planner_builds_recent_days_order_range_plan() -> None:
    plan = await _planner().plan("最近3天椰椰凤梨卖了几单")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.SUMMARY
    assert plan.query_plan.date_from == "2026-07-01"
    assert plan.query_plan.date_to == "2026-07-03"
    assert plan.query_plan.keyword == "椰椰凤梨"


async def test_planner_builds_month_day_order_range_plan() -> None:
    plan = await _planner().plan("7月5日椰椰凤梨卖了几单")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.SUMMARY
    assert plan.query_plan.date_from == "2026-07-05"
    assert plan.query_plan.date_to == "2026-07-05"
    assert plan.query_plan.keyword == "椰椰凤梨"


async def test_planner_builds_weekday_order_range_plan() -> None:
    plan = await _planner().plan("周五椰椰凤梨卖了几单")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.SUMMARY
    assert plan.query_plan.date_from == "2026-07-03"
    assert plan.query_plan.date_to == "2026-07-03"
    assert plan.query_plan.keyword == "椰椰凤梨"


async def test_planner_builds_this_week_order_range_plan() -> None:
    plan = await _planner().plan("本周哪个商品卖得多")

    assert plan.intent == AgentIntent.ORDER_QUERY
    assert plan.query_plan is not None
    assert plan.query_plan.kind == OrderQueryKind.TOP_PRODUCTS
    assert plan.query_plan.date_from == "2026-06-29"
    assert plan.query_plan.date_to == "2026-07-03"
    assert plan.query_plan.keyword == ""


async def test_planner_routes_knowledge_and_ops() -> None:
    knowledge_plan = await _planner().plan("配送范围怎么说")
    casual_delivery_plan = await _planner().plan("明天能配送吗")
    ops_plan = await _planner().plan("系统今天有没有异常")
    integration_plan = await _planner().plan("同步失败有哪些")
    customer_plan = await _planner().plan("查一下张三地址线索")
    campaign_plan = await _planner().plan("汇总 campaignId:abc123")
    offline_review_plan = await _planner().plan("昨晚离线复盘结果")

    assert knowledge_plan.intent == AgentIntent.KNOWLEDGE_ANSWER
    assert casual_delivery_plan.intent == AgentIntent.KNOWLEDGE_ANSWER
    assert ops_plan.intent == AgentIntent.OPS_QUERY
    assert integration_plan.tools == ("integration_status",)
    assert customer_plan.tools == ("customer_lookup",)
    assert campaign_plan.tools == ("group_campaign_summary",)
    assert offline_review_plan.tools == ("offline_review_summary",)


async def test_planner_routes_casual_inventory_question_to_product() -> None:
    plan = await _planner().plan("伯牙绝弦还有吗")

    assert plan.intent == AgentIntent.PRODUCT_QUERY
    assert plan.tools == ("product_lookup",)


async def test_planner_builds_product_knowledge_multi_tool_plan() -> None:
    replacement_plan = await _planner().plan("伯牙绝弦库存不够怎么推荐替代")
    reply_plan = await _planner().plan("伯牙绝弦没货怎么跟客户说")

    assert replacement_plan.intent == AgentIntent.MULTI_TOOL
    assert replacement_plan.tools == ("product_lookup", "knowledge_answer")
    assert replacement_plan.query_plan is None
    assert reply_plan.intent == AgentIntent.MULTI_TOOL
    assert reply_plan.tools == ("product_lookup", "knowledge_answer")
    assert reply_plan.query_plan is None


async def test_planner_gives_llm_all_capabilities_when_search_is_empty(
    monkeypatch,
) -> None:
    captured: dict[str, tuple[str, ...]] = {}

    async def fake_structured_planner(
        query: str,
        capabilities: list[Any],
    ) -> Any:
        captured["capabilities"] = tuple(card.name for card in capabilities)
        return AgentPlan(
            intent=AgentIntent.PRODUCT_QUERY,
            tools=("product_lookup",),
        )

    monkeypatch.setattr(
        employee_agent_planner,
        "request_employee_plan_with_langchain",
        fake_structured_planner,
    )

    plan = await EmployeeAgentPlanner(
        today_provider=lambda: date(2026, 7, 3),
        enable_llm=True,
    ).plan("伯牙绝弦")

    assert plan.intent == AgentIntent.PRODUCT_QUERY
    assert "product_lookup" in captured["capabilities"]
    assert "order_dynamic_query" in captured["capabilities"]


async def test_employee_agent_uses_order_lookup_service() -> None:
    order_lookup_service = _FakeOrderLookupService()
    service = EmployeeAgentService(
        business_tool_service=_FakeBusinessToolService(),
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        order_lookup_service=order_lookup_service,
        planner=_planner(),
    )

    reply = await service.answer("今天一共多少订单")

    assert "今天共 2 单" in reply
    assert "下一步：需要处理待发货订单。" in reply
    assert order_lookup_service.calls[0][1].kind == OrderQueryKind.SUMMARY


async def test_employee_agent_order_reply_does_not_ask_for_full_order_no() -> None:
    service = EmployeeAgentService(
        business_tool_service=_FakeBusinessToolService(),
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        order_lookup_service=_FakeOrderLookupService(),
        planner=_planner(),
    )

    reply = await service.answer("今天一共多少订单")

    assert "完整订单号" not in reply
    assert "订单尾号" not in reply or "完整" not in reply


async def test_employee_agent_routes_product_and_knowledge() -> None:
    business_tool_service = _FakeBusinessToolService()
    service = EmployeeAgentService(
        business_tool_service=business_tool_service,
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        planner=_planner(),
    )

    product_reply = await service.answer("草莓蛋糕还有库存吗")
    knowledge_reply = await service.answer("配送范围怎么说")

    assert "库存 6" in product_reply
    assert "配送范围" in knowledge_reply
    assert business_tool_service.product_payloads[0]["query"] == "草莓蛋糕还有库存吗"


async def test_employee_agent_multi_tool_uses_order_keyword_for_product() -> None:
    business_tool_service = _FakeBusinessToolService()
    service = EmployeeAgentService(
        business_tool_service=business_tool_service,
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        order_lookup_service=_FakeOrderLookupService(),
        planner=_planner(),
    )

    await service.answer("今天订单里有伯牙绝弦吗，库存还够吗")

    assert business_tool_service.product_payloads[0]["query"] == "伯牙绝弦"


async def test_employee_agent_multi_tool_combines_order_and_knowledge() -> None:
    service = EmployeeAgentService(
        business_tool_service=_FakeBusinessToolService(),
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        order_lookup_service=_FakeOrderLookupService(),
        planner=_planner(),
    )

    reply = await service.answer("还有哪些没发货，怎么跟客户说")

    assert "今天共 2 单" in reply
    assert "给客户可复制回复" in reply
    assert "订单目前还在备货处理中" in reply
    assert "知识库回复：还有哪些没发货，怎么跟客户说。" in reply


async def test_employee_agent_multi_tool_combines_product_and_knowledge() -> None:
    business_tool_service = _FakeBusinessToolService()
    service = EmployeeAgentService(
        business_tool_service=business_tool_service,
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        planner=_planner(),
    )

    reply = await service.answer("伯牙绝弦库存不够怎么推荐替代")

    assert "库存 6" in reply
    assert "知识库回复：伯牙绝弦库存不够怎么推荐替代。" in reply
    assert business_tool_service.product_payloads[0]["query"] == (
        "伯牙绝弦库存不够怎么推荐替代"
    )


async def test_employee_agent_product_knowledge_miss_uses_staff_reply() -> None:
    business_tool_service = _FakeBusinessToolServiceWithKnowledgeMiss()
    service = EmployeeAgentService(
        business_tool_service=business_tool_service,
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        planner=_planner(),
    )

    reply = await service.answer("伯牙绝弦库存不够怎么推荐替代")

    assert reply == "当前信息无法可靠确认，我先为您转人工核对，请稍候。"


async def test_employee_agent_high_stock_product_reply_has_no_low_stock_hint() -> None:
    business_tool_service = _FakeBusinessToolServiceWithKnowledgeMiss()
    service = EmployeeAgentService(
        business_tool_service=business_tool_service,
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        planner=_planner(),
    )

    reply = await service.answer("伯牙绝弦还有吗")

    assert "库存 72" in reply
    assert "低库存" not in reply
    assert "库存和价格以小程序商品数据为准" in reply


def test_product_next_action_uses_stock_context() -> None:
    assert "低库存" not in product_next_action("伯牙绝弦还有吗", [_product(72)])
    assert "低库存" in product_next_action("草莓蛋糕还有吗", [_product(3)])
    assert "暂无可售库存" in product_next_action("草莓蛋糕还有吗", [_product(0)])
    assert "未命中结果" in product_next_action("草莓蛋糕还有吗", [])


async def test_employee_agent_routes_existing_ops_tools() -> None:
    service = EmployeeAgentService(
        business_tool_service=_FakeBusinessToolService(),
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        planner=_planner(),
    )

    customer_reply = await service.answer("查一下张三地址线索")
    campaign_reply = await service.answer("汇总 campaignId:abc123")
    offline_review_reply = await service.answer("昨晚离线复盘结果")

    assert "地址/客户线索" in customer_reply
    assert "abc123" in campaign_reply
    assert "离线复盘" in offline_review_reply


async def test_employee_agent_blocks_unauthorized_ops_tool_before_execution() -> None:
    lookup_customer = AsyncMock(return_value={"ok": True, "result": "不应执行"})
    service = EmployeeAgentService(
        business_tool_service=_FakeBusinessToolService(),
        ops_tool_service=SimpleNamespace(lookup_customer=lookup_customer),
        status_tool_service=_FakeStatusToolService(),
        planner=_planner(),
    )

    reply = await service.answer(
        "查一下张三地址线索",
        allowed_tools=frozenset({"order_dynamic_query", "product_lookup"}),
    )

    lookup_customer.assert_not_awaited()
    assert reply == "当前信息无法可靠确认，我先为您转人工核对，请稍候。"


async def test_employee_agent_service_has_no_reply_llm_entrypoint() -> None:
    from app.service.wecom import employee_agent_service

    assert not hasattr(employee_agent_service, "llm_chat")
    assert all(
        not name.startswith("_pol" + "ish") for name in dir(EmployeeAgentService)
    )


async def test_employee_agent_service_delegates_to_langgraph(monkeypatch) -> None:
    from app.service.wecom import employee_agent_service

    class FakeGraphService:
        def __init__(self, dependencies: Any) -> None:
            self.dependencies = dependencies

        async def answer(
            self,
            query: str,
            *,
            allowed_tools: frozenset[str] | None = None,
        ) -> str:
            return f"**graph** {query}"

    monkeypatch.setattr(
        employee_agent_service,
        "EmployeeAgentGraphService",
        FakeGraphService,
    )
    service = EmployeeAgentService(
        business_tool_service=_FakeBusinessToolService(),
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        planner=_planner(),
    )

    reply = await service.answer("草莓蛋糕还有吗")

    assert reply == "graph 草莓蛋糕还有吗"


async def test_employee_agent_product_reply_returns_deterministic_stock() -> None:
    service = EmployeeAgentService(
        business_tool_service=_FakeBusinessToolServiceWithKnowledgeMiss(),
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        planner=_planner(),
    )

    reply = await service.answer("伯牙绝弦还有吗")

    assert "库存 72" in reply
    assert "库存和价格以小程序商品数据为准" in reply
    assert "低库存" not in reply


async def test_employee_agent_no_stock_reply_does_not_invent_replacements() -> None:
    service = EmployeeAgentService(
        business_tool_service=_FakeBusinessToolServiceWithNoStock(),
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        planner=_planner(),
    )

    reply = await service.answer("招牌牛奶吐司还有吗")

    assert "库存 0" in reply
    assert "暂无可售库存" in reply
    assert "不要承诺有货" in reply
    assert "北海道吐司" not in reply
    assert "原味手撕包" not in reply


async def test_employee_agent_product_miss_reply_keeps_guardrail_terms() -> None:
    service = EmployeeAgentService(
        business_tool_service=_FakeBusinessToolServiceWithProductMiss(),
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        planner=_planner(),
    )

    reply = await service.answer("不存在的月球蛋糕还有吗")

    assert reply == "当前信息无法可靠确认，我先为您转人工核对，请稍候。"


async def test_employee_agent_uncertain_operations_query_transfers_to_human() -> None:
    service = EmployeeAgentService(
        business_tool_service=_FakeBusinessToolService(),
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        order_lookup_service=_FakeOrderLookupService(),
        planner=_planner(),
    )

    reply = await service.answer("今天订单有没有需要注意的")

    assert reply == "当前信息无法可靠确认，我先为您转人工核对，请稍候。"


async def test_employee_agent_order_list_reply_keeps_row_shape() -> None:
    service = EmployeeAgentService(
        business_tool_service=_FakeBusinessToolService(),
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        order_lookup_service=_FakePendingOrderListLookupService(),
        planner=_planner(),
    )

    reply = await service.answer("还有哪些没发货")

    assert "尾号 300061｜待发货" in reply
    assert "158.00 元" in reply
    assert "暂无物流" in reply


async def test_employee_agent_reply_cleans_markdown_from_deterministic_result() -> None:
    service = EmployeeAgentService(
        business_tool_service=_FakeBusinessToolService(),
        ops_tool_service=_FakeOpsToolService(),
        status_tool_service=_FakeStatusToolService(),
        order_lookup_service=_FakeMarkdownOrderLookupService(),
        planner=_planner(),
    )

    reply = await service.answer("今天一共多少订单")

    assert "今日销量第一" in reply
    assert "巧克力樱桃炸弹" in reply
    assert "**" not in reply
    assert "`" not in reply


def test_build_top_products_tool_result_marks_low_sample_tie() -> None:
    result = build_top_products_tool_result(
        "今天卖爆的是哪个",
        [
            {
                "product_titles": "巧克力樱桃炸弹",
                "total_quantity": 1,
                "order_count": 1,
                "total_amount_fen": 20650,
            },
            {
                "product_titles": "绿野仙踪蝴蝶款",
                "total_quantity": 1,
                "order_count": 1,
                "total_amount_fen": 27350,
            },
        ],
    )

    assert "销量并列" in result.summary
    assert "不能判断单一爆款" in result.summary
    assert "后续订单趋势" in result.next_action


def test_employee_delivery_time_text_marks_overdue_delivery(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.service.wecom.intelligent_bot_delivery_format.now_beijing_naive",
        lambda: datetime(2026, 7, 4, 12, 0, 0),
    )

    delivery_text = employee_delivery_time_text(
        {"delivery_time": "2026-06-06 11:00:00"}
    )

    assert delivery_text == "约送 2026-06-06 11:00:00（已过约送时间）"


def test_build_order_list_tool_result_labels_fulfillment_risk_order() -> None:
    result = build_order_list_tool_result(
        "哪些单快超时了",
        {"total_count": 1},
        [
            {
                "order_no": "E202607041200101",
                "status": "WAIT_BUYER_CONFIRM_GOODS",
                "product_titles": "水果盛宴 x 1",
                "amount_fen": 31300,
                "pay_time": "2026-06-06 10:00:00",
                "delivery_time": "2026-06-06 11:00:00",
            }
        ],
        OrderQueryPlan(
            needs_fulfillment_risk=True,
            date_field="delivery_time",
            statuses=("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS"),
            sort_by="delivery_time",
        ),
    )

    assert "按约送时间从早到晚展示" in result.summary
    assert "尾号 200101｜待收货" in result.summary
    assert "暂无物流" in result.summary
    assert "已过约送时间" in result.next_action
