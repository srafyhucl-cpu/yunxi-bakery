"""
有赞历史脏数据一键修复与商品编码全量补齐脚本。

职责：
1. 以有赞线上真实的在售商品列表（Golden Standard）为唯一基准。
2. 将所有真实的在售商品在本地 youzan_products 和 knowledge_base 表中的状态一键恢复/对齐为在售（is_active=1），修复历史对账误下架的商品。
3. 将所有真实已下架的商品在本地两张表中的状态一键同步为下架（is_active=0）。
4. 自动拉取并补齐数据库中空缺的商品编码（item_no）与最新销量，以打通同款商品的销量自动合并。
"""

import asyncio
import os
import sys

# 强行设置标准输出编码为 UTF-8，防止商品标题中的 Emoji 导致 Windows GBK 终端报错
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# 将项目根目录加入 Path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import init_db
from app.config import settings
from app.service.youzan.client import YouzanClient
from app.repository.config_repo import ConfigRepo


async def main() -> None:
    print("=== 启动有赞数据状态全量校准与编码自愈通道 ===")

    # 强制激活真实有赞平台连通
    settings.YOUZAN_MOCK_MODE = False
    db_path = "data/bot.db"
    db = await init_db(db_path)

    try:
        config_repo = ConfigRepo(db)
        yz_client = YouzanClient(config_repo=config_repo)

        # 1. 从有赞 API 获取最新真实的在线在售商品列表
        print("[1] 正在从有赞 API 抓取在线在售商品列表...")
        items = await yz_client.list_onsale_items()
        onsale_ids = [int(item["item_id"]) for item in items]
        print(f"  - 真实在线在售商品共: {len(onsale_ids)} 个")

        if not onsale_ids:
            print(
                "❌ 未拉取到任何在线商品，请检查有赞 API 配置，暂不执行状态校准以防误伤。"
            )
            return

        # 2. 全量状态校准（以有赞在售列表为唯一准则）
        print("[2] 正在进行商品在售状态全量校准对齐...")

        # 构造 SQL 参数占位符
        placeholders = ",".join("?" * len(onsale_ids))

        # 将有赞在售的商品，在 youzan_products 和 knowledge_base 里全部恢复为在售 (is_active=1)
        cursor_yp_active = await db.execute(
            f"UPDATE youzan_products SET is_active = 1 WHERE item_id IN ({placeholders}) AND is_active = 0",
            tuple(onsale_ids),
        )
        cursor_kb_active = await db.execute(
            f"UPDATE knowledge_base SET is_active = 1 WHERE youzan_item_id IN ({placeholders}) AND is_active = 0 AND category = 'product'",
            tuple(map(str, onsale_ids)),
        )

        # 将不在有赞在售的商品，在 youzan_products 和 knowledge_base 里全部标记为下架 (is_active=0)
        cursor_yp_inactive = await db.execute(
            f"UPDATE youzan_products SET is_active = 0 WHERE item_id NOT IN ({placeholders}) AND is_active = 1",
            tuple(onsale_ids),
        )
        cursor_kb_inactive = await db.execute(
            f"UPDATE knowledge_base SET is_active = 0 WHERE youzan_item_id NOT IN ({placeholders}) AND is_active = 1 AND category = 'product'",
            tuple(map(str, onsale_ids)),
        )

        await db.commit()

        print(
            f"  - [youzan_products] 表状态校准: 恢复上架 {cursor_yp_active.rowcount} 个，联动下架 {cursor_yp_inactive.rowcount} 个"
        )
        print(
            f"  - [knowledge_base] 表状态校准: 恢复上架 {cursor_kb_active.rowcount} 个，联动下架 {cursor_kb_inactive.rowcount} 个"
        )

        # 3. 补齐商品编码 item_no
        print("[3] 正在获取数据库中商品编码为空的商品记录...")
        rows = await db.execute_fetchall(
            "SELECT item_id, title FROM youzan_products WHERE item_no = '' OR item_no IS NULL"
        )
        print(f"  - 共找到 {len(rows)} 个商品编码为空的本地商品记录")

        if rows:
            sem = asyncio.Semaphore(10)
            updated_count = 0
            failed_count = 0

            async def _fetch_and_update(iid: int, title: str) -> None:
                nonlocal updated_count, failed_count
                async with sem:
                    try:
                        raw = await yz_client.get_product(iid)
                        item = (raw.get("data") or raw.get("response") or {}).get(
                            "item"
                        ) or {}
                        item_no = item.get("item_no", "") or ""
                        sold_num = int(item.get("sold_num", 0) or 0)

                        # 强制写入数据库
                        await db.execute(
                            "UPDATE youzan_products SET item_no = ?, sold_num = ? WHERE item_id = ?",
                            (item_no, sold_num, iid),
                        )
                        await db.commit()
                        print(
                            f"    [OK] 补齐 [{title}] (ID: {iid}) -> 编码: {item_no}, 销量: {sold_num}"
                        )
                        updated_count += 1
                    except Exception as exc:
                        print(f"    [ERROR] 补齐 [{title}] (ID: {iid}) 失败: {exc}")
                        failed_count += 1

            tasks = [_fetch_and_update(row["item_id"], row["title"]) for row in rows]
            await asyncio.gather(*tasks)
            print(
                f"\n编码补齐与销量回写执行完毕！成功: {updated_count}，失败: {failed_count}"
            )

        await yz_client.close()
        print("\n🏆 全量状态对齐与编码自愈任务完美结束！")

    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
