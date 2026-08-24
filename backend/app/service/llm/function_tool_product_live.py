"""商品实时查询、缓存和 RAG 回写。"""

from __future__ import annotations

import datetime
import json
from typing import TYPE_CHECKING

from app.logger import setup_logger
from app.models.content_change_history import (
    ChangeAction,
    ChangeEntityType,
    SyncSource,
    WriteResult,
)
from app.service.observability import ContentChangeLogger, build_product_change_summary
from app.utils import now_beijing_naive, now_str

if TYPE_CHECKING:
    from app.service.youzan.client import YouzanClient

logger = setup_logger()

PRODUCT_CACHE_TTL_SECONDS = 300


async def get_cached_product_if_fresh(item_id: int, product_repo) -> dict | None:
    """读取 TTL 内仍然有效的商品缓存。"""
    product = await product_repo.get_by_id(item_id)
    if not product or not product.get("updated_at"):
        return None
    try:
        updated_dt = datetime.datetime.strptime(
            product["updated_at"], "%Y-%m-%d %H:%M:%S"
        )
    except ValueError:
        return None
    age_seconds = (now_beijing_naive() - updated_dt).total_seconds()
    if age_seconds > PRODUCT_CACHE_TTL_SECONDS:
        return None
    logger.debug("商品 TTL 缓存命中: item_id=%s age_seconds=%.1f", item_id, age_seconds)
    return {
        "item_id": item_id,
        "title": product["title"],
        "price_fen": product["price_fen"],
        "stock": product["stock"],
        "tags": product.get("tags", ""),
        "updated_at": product["updated_at"],
        "desc": product.get("desc", ""),
        "skus": json.loads(product.get("skus_json") or "[]"),
    }


async def refresh_product_live(
    item_id: int,
    youzan_client: YouzanClient,
    product_repo,
    knowledge_product_repo,
    embedding_searcher,
    history_repo,
) -> dict | None:
    """调用有赞 API 刷新商品宽表、知识库和向量索引。"""
    from app.service.youzan.product_sync import (
        build_tags_str,
        parse_product_from_api,
        sync_product_to_db,
        sync_product_to_rag,
    )

    history_logger = ContentChangeLogger(history_repo)

    try:
        raw = await youzan_client.get_product(item_id)
        if isinstance(raw, dict) and raw.get("gw_err_resp"):
            logger.error(
                "商品实时刷新 API 拒绝: item_id=%s err=%s", item_id, raw["gw_err_resp"]
            )
            await history_logger.log_failed(
                entity_type=ChangeEntityType.PRODUCT,
                entity_key=str(item_id),
                category="product",
                title=f"商品 {item_id}",
                source=SyncSource.CHAT_LIVE_REFRESH,
                source_ref=str(item_id),
                action=ChangeAction.UPSERT,
                error_type="gw_err_resp",
                error_message=str(raw["gw_err_resp"]),
            )
            return None

        parsed = parse_product_from_api(raw, item_id)
        if parsed is None:
            logger.error("商品实时刷新响应结构异常: item_id=%s", item_id)
            await history_logger.log_failed(
                entity_type=ChangeEntityType.PRODUCT,
                entity_key=str(item_id),
                category="product",
                title=f"商品 {item_id}",
                source=SyncSource.CHAT_LIVE_REFRESH,
                source_ref=str(item_id),
                action=ChangeAction.UPSERT,
                error_type="missing_item",
                error_message="商品接口响应缺少 item",
            )
            return None

        local_product = await product_repo.get_by_id(item_id)
        old_active = local_product["is_active"] if local_product else 1
        tags_str = build_tags_str(parsed, "在售")
        updated_at = now_str()
        product_result = await sync_product_to_db(
            product_repo,
            parsed,
            old_active,
            updated_at,
            tags_str,
            SyncSource.CHAT_LIVE_REFRESH,
            str(item_id),
        )
        knowledge_result = await sync_product_to_rag(
            knowledge_product_repo,
            embedding_searcher,
            parsed,
            1,
            tags_str,
            "在售",
            updated_at,
            SyncSource.CHAT_LIVE_REFRESH,
            str(item_id),
        )
        if (
            product_result == WriteResult.APPLIED
            or knowledge_result == WriteResult.APPLIED
        ):
            await history_logger.log_success(
                entity_type=ChangeEntityType.PRODUCT,
                entity_key=str(item_id),
                category="product",
                title=parsed["title"],
                source=SyncSource.CHAT_LIVE_REFRESH,
                source_ref=str(item_id),
                action=ChangeAction.UPSERT,
                change_summary=build_product_change_summary(
                    item_id=item_id,
                    title=parsed["title"],
                    alias=parsed["alias"],
                    price_fen=parsed["price_fen"],
                    stock=parsed["stock"],
                    is_active=1,
                    tags=tags_str,
                    updated_at=updated_at,
                    product_result=product_result,
                    knowledge_result=knowledge_result,
                ),
                occurred_at=updated_at,
            )
        logger.info(
            "商品实时刷新写入成功: item_id=%s title=%s", item_id, parsed["title"]
        )
        return {
            "item_id": item_id,
            "title": parsed["title"],
            "price_fen": parsed["price_fen"],
            "stock": parsed["stock"],
            "tags": tags_str,
            "updated_at": updated_at,
        }
    except Exception as exc:
        logger.error("商品实时刷新失败: item_id=%s err=%s", item_id, exc)
        await history_logger.log_failed(
            entity_type=ChangeEntityType.PRODUCT,
            entity_key=str(item_id),
            category="product",
            title=f"商品 {item_id}",
            source=SyncSource.CHAT_LIVE_REFRESH,
            source_ref=str(item_id),
            action=ChangeAction.UPSERT,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        return None
