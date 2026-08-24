"""客户机器人 LangChain 工具注册表测试。"""

import json
import sys

import pytest

from app.service.agents.tools.customer import CustomerToolContext


def test_tool_registry_import_does_not_load_langchain_runtime() -> None:
    sys.modules.pop("app.service.agents.tools.registry", None)
    sys.modules.pop("langchain_core.tools", None)

    import app.service.agents.tools.registry  # noqa: F401

    assert "langchain_core.tools" not in sys.modules


def test_customer_tool_names_match_legacy_function_definitions() -> None:
    from app.service.agents.tools.customer import build_customer_openai_tool_definitions
    from app.service.agents.tools.registry import build_tools

    schema_names = {
        item["function"]["name"]
        for item in build_customer_openai_tool_definitions()
        if item.get("type") == "function"
    }
    tools = build_tools("customer", customer_context=CustomerToolContext())

    assert {tool.name for tool in tools} == schema_names


@pytest.mark.asyncio
async def test_customer_tool_fallback_keeps_json_contract() -> None:
    from app.service.agents.tools.registry import build_tools

    tools = {
        tool.name: tool
        for tool in build_tools("customer", customer_context=CustomerToolContext())
    }
    actual = await tools["search_knowledge"].ainvoke({"query": "配送范围"})

    assert json.loads(actual) == {"message": "知识库服务暂不可用"}


@pytest.mark.asyncio
async def test_transfer_tool_uses_injected_handler() -> None:
    from app.service.agents.tools.registry import build_tools

    async def transfer_handler(reason: str) -> str:
        return json.dumps({"status": "success", "reason": reason}, ensure_ascii=False)

    tools = {
        tool.name: tool
        for tool in build_tools(
            "customer",
            customer_context=CustomerToolContext(transfer_handler=transfer_handler),
        )
    }

    result = await tools["transfer_to_human"].ainvoke({"reason": "需要人工"})

    assert json.loads(result) == {"status": "success", "reason": "需要人工"}
