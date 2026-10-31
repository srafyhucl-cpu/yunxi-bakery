"""把商品图片从有赞 CDN 迁移到服务器本地。

用法：
    python scripts/sync_product_images.py --limit 20      # 先跑 20 条试水
    python scripts/sync_product_images.py                 # 全量迁移
    python scripts/sync_product_images.py --dry-run       # 只统计不下载

行为：
    - 只处理 image 为 http(s) 且 image_local 为空、或本地文件已丢失的商品；
    - 下载到 <数据库目录>/product-images/<item_id>.<ext>，并把相对路径写回 image_local；
    - 单张超过 5MB 或内容类型不是图片时跳过并记录，不阻塞整批；
    - 重复执行安全：已有本地文件直接补写数据库，不重复下载。
"""

from __future__ import annotations

import argparse
import logging
import mimetypes
import os
import sqlite3
import time
from pathlib import Path

import httpx

MAX_IMAGE_BYTES = 5 * 1024 * 1024
IMAGE_DIR_NAME = "product-images"
DEFAULT_TIMEOUT_SECONDS = 15.0
PROGRESS_EVERY = 25

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("sync_product_images")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="迁移商品图片到服务器本地")
    parser.add_argument(
        "--limit", type=int, default=0, help="最多处理多少个商品，0 表示全部"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="只统计待迁移数量，不下载"
    )
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    return parser.parse_args()


def resolve_paths() -> tuple[Path, Path]:
    db_path = Path(os.environ.get("DB_PATH", "data/bot.db")).resolve()
    if not db_path.is_file():
        raise SystemExit(f"数据库不存在：{db_path}")
    image_dir = db_path.parent / IMAGE_DIR_NAME
    return db_path, image_dir


def list_pending(db_path: Path, limit: int) -> list[tuple[int, str, str]]:
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            "SELECT item_id, image, image_local FROM youzan_products "
            "WHERE image LIKE 'http%' ORDER BY item_id"
        ).fetchall()
    finally:
        conn.close()
    pending: list[tuple[int, str, str]] = []
    for item_id, image, image_local in rows:
        relative = str(image_local or "").strip()
        if relative and (db_path.parent / relative).is_file():
            continue
        pending.append((int(item_id), str(image), relative))
        if limit and len(pending) >= limit:
            break
    return pending


def pick_extension(content_type: str, source_url: str) -> str:
    normalized = (content_type or "").split(";")[0].strip().lower()
    guessed = mimetypes.guess_extension(normalized) if normalized else None
    if guessed in (".jpg", ".jpeg", ".png", ".webp"):
        return ".jpg" if guessed == ".jpeg" else guessed
    suffix = Path(source_url.split("?")[0]).suffix.lower()
    return suffix if suffix in (".jpg", ".jpeg", ".png", ".webp") else ".jpg"


def download(client: httpx.Client, url: str) -> tuple[bytes, str] | None:
    try:
        response = client.get(url)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("下载失败 %s：%s", url, exc)
        return None
    content_type = response.headers.get("content-type", "")
    if not content_type.startswith("image/"):
        logger.warning("非图片内容 %s：%s", url, content_type)
        return None
    content = response.content
    if not content or len(content) > MAX_IMAGE_BYTES:
        logger.warning("图片体积异常 %s：%s 字节", url, len(content))
        return None
    return content, content_type


def write_local(image_dir: Path, item_id: int, content: bytes, extension: str) -> str:
    image_dir.mkdir(parents=True, exist_ok=True)
    target = image_dir / f"{item_id}{extension}"
    target.write_bytes(content)
    return f"{IMAGE_DIR_NAME}/{target.name}"


def update_local_path(db_path: Path, item_id: int, relative: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "UPDATE youzan_products SET image_local = ? WHERE item_id = ?",
            (relative, item_id),
        )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    args = parse_args()
    db_path, image_dir = resolve_paths()
    pending = list_pending(db_path, args.limit)
    logger.info("待迁移商品 %s 个，图片目录 %s", len(pending), image_dir)
    if args.dry_run or not pending:
        return 0

    started = time.time()
    migrated = 0
    failed = 0
    with httpx.Client(
        timeout=args.timeout,
        follow_redirects=True,
        headers={"User-Agent": "yunxi-product-image-migrator/1.0"},
    ) as client:
        for index, (item_id, image, existing_local) in enumerate(pending, start=1):
            if existing_local:
                # 本地文件丢了但数据库还有记录：重新下载并覆盖同一路径
                logger.info("本地文件缺失，重新下载 item_id=%s", item_id)
            result = download(client, image)
            if result is None:
                failed += 1
                continue
            content, content_type = result
            extension = pick_extension(content_type, image)
            relative = write_local(image_dir, item_id, content, extension)
            update_local_path(db_path, item_id, relative)
            migrated += 1
            if index % PROGRESS_EVERY == 0:
                logger.info(
                    "进度 %s/%s，成功 %s，失败 %s",
                    index,
                    len(pending),
                    migrated,
                    failed,
                )

    logger.info(
        "完成：成功 %s，失败 %s，耗时 %.1fs",
        migrated,
        failed,
        time.time() - started,
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
