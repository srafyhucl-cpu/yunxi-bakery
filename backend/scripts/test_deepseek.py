"""
DeepSeek API 连接测试。

显示完整的请求和响应内容，方便调试。
用法: python scripts/test_deepseek.py
"""

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


from openai import AsyncOpenAI

from app.config import settings


async def test_deepseek() -> None:
    print("=" * 60)
    print("配置信息")
    print("=" * 60)
    print(f"  模型:         {settings.DEEPSEEK_MODEL}")
    print(f"  API 地址:     {settings.DEEPSEEK_BASE_URL}")
    print(
        f"  API Key:      {settings.DEEPSEEK_API_KEY[:8]}...{settings.DEEPSEEK_API_KEY[-4:]}"
    )

    client = AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )

    messages = [
        {"role": "system", "content": "你是芸熙烘焙的智能客服，回答简洁友好。"},
        {"role": "user", "content": "提拉米苏多少钱？"},
    ]

    print("\n" + "=" * 60)
    print("发送请求 (Request)")
    print("=" * 60)
    print("\n请求参数:")
    print(
        json.dumps(
            {
                "model": settings.DEEPSEEK_MODEL,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1024,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

    print(f"\n{'=' * 60}")
    print("接收响应 (Response)")
    print("=" * 60)

    response = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=messages,  # type: ignore[arg-type]
        temperature=0.7,
        max_tokens=1024,
    )

    print("\n完整响应:")
    print(json.dumps(response.model_dump(), ensure_ascii=False, indent=2, default=str))

    print(f"\n{'=' * 60}")
    print("关键字段提取")
    print("=" * 60)
    choice = response.choices[0]
    print(f"  finish_reason:   {choice.finish_reason}")
    print(f"  AI 回复内容:     {choice.message.content}")
    if response.usage is not None:
        print(f"  总 Token 数:     {response.usage.total_tokens}")
        print(f"  输入 Token 数:   {response.usage.prompt_tokens}")
        print(f"  输出 Token 数:   {response.usage.completion_tokens}")


if __name__ == "__main__":
    asyncio.run(test_deepseek())
