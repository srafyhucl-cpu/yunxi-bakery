"""顾客端 AI 工具只读边界与定制需求卡工具测试。"""

import json
from datetime import timedelta

import aiosqlite
import pytest

from app.service.agents.tools.customer import CustomerToolContext
from app.service.agents.tools.registry import build_tools
from app.utils import now_beijing

# 顾客端只允许只读查询、受控转人工与定制需求卡三类能力。
EXPECTED_CUSTOMER_TOOL_NAMES = {
    "get_order_info",
    "get_product_info",
    "get_logistics_info",
    "search_knowledge",
    "transfer_to_human",
    "build_customization_card",
}

# 任何写库、改单、扣款类工具名都不得出现在顾客端工具清单里。
FORBIDDEN_TOOL_KEYWORDS = (
    "create",
    "update",
    "cancel",
    "delete",
    "pay",
    "refund",
    "deduct",
    "charge",
    "recharge",
    "withdraw",
    "stock",
)


def _tools() -> dict:
    return {
        tool.name: tool
        for tool in build_tools("customer", customer_context=CustomerToolContext())
    }


async def _count_orders(db: aiosqlite.Connection) -> int:
    rows = await db.execute_fetchall("SELECT COUNT(*) FROM orders")
    return int(rows[0][0])


def test_customer_tool_list_is_readonly_plus_card() -> None:
    """工具清单只包含只读查询、转人工与定制需求卡。"""
    names = set(_tools())

    assert names == EXPECTED_CUSTOMER_TOOL_NAMES


def test_customer_tool_list_has_no_write_tools() -> None:
    """不得出现建单、改单、扣款类写工具。"""
    for name in _tools():
        lowered = name.lower()
        assert not any(keyword in lowered for keyword in FORBIDDEN_TOOL_KEYWORDS)


def test_openai_tool_schema_matches_langchain_tools() -> None:
    """OpenAI tool schema 与 LangChain 工具清单保持一致。"""
    from app.service.agents.tools.customer import (
        build_customer_openai_tool_definitions,
    )

    schema_names = {
        item["function"]["name"]
        for item in build_customer_openai_tool_definitions()
        if item.get("type") == "function"
    }

    assert schema_names == EXPECTED_CUSTOMER_TOOL_NAMES


@pytest.mark.asyncio
async def test_customization_card_tool_returns_card_without_creating_orders(
    db: aiosqlite.Connection,
) -> None:
    """定制卡工具只返回结构化文本，不建单、不写库。"""
    tools = _tools()

    result = await tools["build_customization_card"].ainvoke(
        {
            "size": "8寸",
            "filling": "芒果慕斯",
            "greeting": "生日快乐",
            "accessories": "蜡烛、餐具",
            "expectTime": (now_beijing() + timedelta(days=1)).strftime(
                "%Y-%m-%d %H:%M"
            ),
        }
    )

    card = json.loads(result)
    assert card["size"] == "8寸"
    assert card["filling"] == "芒果慕斯"
    assert card["sweetness"] == "8分甜"
    assert card["greeting"] == "生日快乐"
    assert card["accessories"] == "蜡烛、餐具"
    assert card["expectTime"]
    assert "尺寸：8寸" in card["summary"]
    assert await _count_orders(db) == 0


@pytest.mark.asyncio
async def test_customization_card_tool_rejects_missing_field() -> None:
    """缺必填项时工具直接报错，不生成半成品需求卡。"""
    tools = _tools()

    with pytest.raises(ValueError):
        await tools["build_customization_card"].ainvoke({"size": "8寸"})


@pytest.mark.asyncio
async def test_customization_card_tool_rejects_expect_time_within_four_hours() -> None:
    """预约时间不足四小时时工具直接报错。"""
    tools = _tools()
    expect_time = (now_beijing() + timedelta(hours=1)).strftime("%Y-%m-%d %H:%M")

    with pytest.raises(ValueError):
        await tools["build_customization_card"].ainvoke(
            {
                "size": "8寸",
                "filling": "芒果慕斯",
                "greeting": "生日快乐",
                "accessories": "蜡烛、餐具",
                "expectTime": expect_time,
            }
        )
