"""
测试知识库注入后 AI 能否准确回答真实价格。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from openai import AsyncOpenAI
from app.config import settings
from app.repository.knowledge_repo import KnowledgeRepo
from app.database import init_db
from app.service.llm.prompt import build_system_prompt


async def test():
    # 1. 从知识库搜索提拉米苏
    db = await init_db("data/bot.db")
    repo = KnowledgeRepo(db)
    results = await repo.search("提拉米苏", limit=5)

    print("=" * 60)
    print("知识库命中:")
    for r in results:
        print(f"  {r.title} → {r.content[:100]}")
    print()

    # 2. 构建 system prompt（注入知识）
    system_prompt = build_system_prompt(results)

    # 3. 调用 DeepSeek
    client = AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )

    response = await client.chat.completions.create(
        model=settings.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "提拉米苏多少钱？"},
        ],  # type: ignore[arg-type]
        temperature=0.7,
        max_tokens=1024,
    )

    print("AI 回复:")
    print(f"  {response.choices[0].message.content}")
    print(f"\n基于知识库真实数据 (total_tokens={response.usage.total_tokens})")

    await db.close()


asyncio.run(test())
