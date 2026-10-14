import aiosqlite
import asyncio


async def c():
    conn = await aiosqlite.connect("data/bot.db")
    conn.row_factory = aiosqlite.Row
    rows = await conn.execute_fetchall(
        "SELECT title, content FROM knowledge_base WHERE title LIKE ? LIMIT 3",
        ("%提拉米苏%",),
    )
    for r in rows:
        print(f"--- {r['title']} ---")
        print(r["content"][:300])
        print()
    # 查看一条完整的产品数据看看结构
    row2 = await conn.execute_fetchall(
        "SELECT title, content FROM knowledge_base WHERE category='product' LIMIT 1"
    )
    if row2:
        print(f"--- 示例产品: {row2[0]['title']} ---")
        print(row2[0]["content"])
    await conn.close()


asyncio.run(c())
