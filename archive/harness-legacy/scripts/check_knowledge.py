"""
验证知识库数据。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import asyncio
import aiosqlite


async def check():
    conn = await aiosqlite.connect("data/bot.db")
    conn.row_factory = aiosqlite.Row

    rows = await conn.execute_fetchall(
        "SELECT category, COUNT(*) as c FROM knowledge_base GROUP BY category ORDER BY c DESC"
    )
    print("知识库统计:")
    for r in rows:
        print(f"  {r['category']}: {r['c']} 条")

    rows2 = await conn.execute_fetchall(
        "SELECT title, content FROM knowledge_base WHERE keywords LIKE '%提拉米苏%' LIMIT 3"
    )
    print("\n搜索 '提拉米苏':")
    for r in rows2:
        print(f"  {r['title']}")
        print(f"  → {r['content'][:80]}")

    rows3 = await conn.execute_fetchall("SELECT COUNT(*) as c FROM knowledge_base")
    print(f"\n总计: {rows3[0]['c']} 条知识")

    await conn.close()


asyncio.run(check())
