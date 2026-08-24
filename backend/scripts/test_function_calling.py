"""
Function Calling 测试。

显示完整的请求和响应，验证工具调用是否正常。
用法: python scripts/test_function_calling.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import AsyncOpenAI

from app.config import settings
from app.service.agents.tools.customer import build_customer_openai_tool_definitions

CUSTOMER_OPENAI_TOOLS = build_customer_openai_tool_definitions()


async def test_function_calling() -> None:
    client = AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )

    # =========================================
    # 场景 1：用户查订单
    # =========================================
    messages = [
        {
            "role": "system",
            "content": "你是芸熙烘焙的智能客服。可以通过工具查询订单信息。",
        },
        {"role": "user", "content": "帮我查一下订单 E20240516001 到哪了"},
    ]

    print("=" * 60)
    print("场景 1：用户查询订单")
    print("=" * 60)
    print("\n【请求参数】")
    payload = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": messages,
        "tools": CUSTOMER_OPENAI_TOOLS,
        "temperature": 0.7,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    print("\n【响应结果】")
    response = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=messages,  # type: ignore[arg-type]
        tools=CUSTOMER_OPENAI_TOOLS,
        temperature=0.7,
    )
    print(json.dumps(response.model_dump(), ensure_ascii=False, indent=2, default=str))

    choice = response.choices[0]
    print(f"\n→ finish_reason: {choice.finish_reason}")
    if choice.finish_reason == "tool_calls" and choice.message.tool_calls:
        for tc in choice.message.tool_calls:
            print(f"→ 调用的工具: {tc.function.name}")
            print(f"→ 工具参数: {tc.function.arguments}")

    # =========================================
    # 场景 2：用户要求转人工
    # =========================================
    messages2 = [
        {
            "role": "system",
            "content": "你是芸熙烘焙的智能客服。当用户要求转人工时可以调用工具。",
        },
        {"role": "user", "content": "我要投诉，转人工客服"},
    ]

    print(f"\n{'=' * 60}")
    print("场景 2：用户要求转人工")
    print("=" * 60)
    print("\n【请求参数】")
    payload2 = {
        "model": settings.DEEPSEEK_MODEL,
        "messages": messages2,
        "tools": CUSTOMER_OPENAI_TOOLS,
        "temperature": 0.7,
    }
    print(json.dumps(payload2, ensure_ascii=False, indent=2))

    print("\n【响应结果】")
    response2 = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=messages2,  # type: ignore[arg-type]
        tools=CUSTOMER_OPENAI_TOOLS,
        temperature=0.7,
    )
    print(json.dumps(response2.model_dump(), ensure_ascii=False, indent=2, default=str))

    choice2 = response2.choices[0]
    print(f"\n→ finish_reason: {choice2.finish_reason}")
    if choice2.finish_reason == "tool_calls" and choice2.message.tool_calls:
        for tc in choice2.message.tool_calls:
            print(f"→ 调用的工具: {tc.function.name}")
            print(f"→ 工具参数: {tc.function.arguments}")


if __name__ == "__main__":
    asyncio.run(test_function_calling())
