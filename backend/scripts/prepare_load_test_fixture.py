"""为 CI 并发压测准备最小 SQLite 测试数据。"""

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from app.database import close_db, init_db, resolve_database_path  # noqa: E402
from app.config import settings  # noqa: E402


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="准备 CI 并发压测数据")
    parser.add_argument(
        "--db-path",
        default=settings.DB_PATH,
        help="目标 SQLite 数据库路径，默认读取 DB_PATH。",
    )
    parser.add_argument(
        "--orders",
        type=int,
        default=10,
        help="写入的测试订单数量。",
    )
    parser.add_argument(
        "--products",
        type=int,
        default=10,
        help="写入的测试商品数量。",
    )
    return parser.parse_args()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def _seed_orders(db_path: str, count: int) -> None:
    now = _now()
    async with aiosqlite.connect(db_path) as db:
        for index in range(max(count, 1)):
            order_no = f"ci_load_order_{index:04d}"
            await db.execute(
                "INSERT OR REPLACE INTO youzan_orders ("
                "order_no, buyer_id, status, amount_fen, product_titles, "
                "total_quantity, order_items_json, created_at, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    order_no,
                    f"ci_buyer_{index:04d}",
                    "WAIT_SELLER_SEND_GOODS",
                    18800,
                    "CI 压测草莓蛋糕",
                    1,
                    json.dumps(
                        [
                            {
                                "title": "CI 压测草莓蛋糕",
                                "num": 1,
                                "price_fen": 18800,
                            }
                        ],
                        ensure_ascii=False,
                    ),
                    now,
                    now,
                ),
            )
        await db.commit()


async def _seed_products(db_path: str, count: int) -> None:
    now = _now()
    async with aiosqlite.connect(db_path) as db:
        for index in range(max(count, 1)):
            item_id = 900000000 + index
            await db.execute(
                "INSERT OR REPLACE INTO youzan_products ("
                "item_id, title, alias, price_fen, stock, image, is_active, "
                "skus_json, item_props_json, desc, tags, updated_at"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    item_id,
                    f"CI 压测商品 {index:02d}",
                    f"ci-load-product-{index:02d}",
                    28800,
                    100,
                    "https://img.yzcdn.cn/fake-ci-load-test.jpg",
                    1,
                    "[]",
                    "[]",
                    "CI 并发压测商品数据",
                    "压测,CI,蛋糕",
                    now,
                ),
            )
        await db.commit()


async def main() -> int:
    args = _parse_args()
    resolved_db_path = resolve_database_path(args.db_path)
    Path(resolved_db_path).parent.mkdir(parents=True, exist_ok=True)

    db = await init_db(resolved_db_path)
    await close_db(db)
    await _seed_orders(resolved_db_path, args.orders)
    await _seed_products(resolved_db_path, args.products)

    print(
        "CI load-test fixture ready: "
        f"db={resolved_db_path} orders={max(args.orders, 1)} "
        f"products={max(args.products, 1)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
