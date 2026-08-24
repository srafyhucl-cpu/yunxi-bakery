"""
测试 DeepSeek Embedding API — 尝试不同模型名。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
from openai import AsyncOpenAI
from app.config import settings


async def test():
    client = AsyncOpenAI(
        api_key=settings.DEEPSEEK_API_KEY,
        base_url=settings.DEEPSEEK_BASE_URL,
    )

    texts = ["提拉米苏48元", "草莓蛋糕168元"]

    # 常见的中文 embedding 模型名
    models = [
        "deepseek-embedding",  # 官方主推
        "bge-large-zh",
    ]

    for model in models:
        try:
            resp = await client.embeddings.create(model=model, input=texts)
            dim = len(resp.data[0].embedding)
            print(f"✅ {model} → 维度: {dim}")

            # 验证两个向量的维度一致
            print(f"   第1条向量长度: {len(resp.data[0].embedding)}")
            print(f"   第2条向量长度: {len(resp.data[1].embedding)}")

        except Exception as e:
            print(f"❌ {model} → {e}")


asyncio.run(test())
