"""一键测试四个核心场景"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import httpx


async def test():
    url = "http://127.0.0.1:7001/api/v1/admin/chat-test"
    headers = {"Authorization": "Bearer 100200"}

    tests = [
        ("🍰 提拉米苏多少钱", {"content": "提拉米苏多少钱", "user_id": "test_1"}),
        ("☕ 美式咖啡", {"content": "美式咖啡有吗", "user_id": "test_2"}),
        ("🚚 运费谁出", {"content": "明天下午能送到吗运费谁出", "user_id": "test_3"}),
        ("🔔 转人工", {"content": "转人工", "user_id": "test_4"}),
    ]

    async with httpx.AsyncClient() as c:
        for label, payload in tests:
            r = await c.post(url, json=payload, headers=headers, timeout=30)
            data = r.json()
            reply = data.get("reply", "")[:200]
            intent = {1: "商品", 2: "运费", 3: "配送", 4: "售后", 5: "闲聊"}.get(
                data.get("intent"), "?"
            )
            print(f"[{intent}] {label}")
            print(f"  → {reply}")
            print()


asyncio.run(test())
