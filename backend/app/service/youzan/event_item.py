"""
有赞商品事件处理器。

处理有赞 Webhook 推送的商品上下架及属性变更事件（item_*）：
- 物理宽表 Upsert（youzan_products）
- RAG 增量知识库同步（上架更新 / 下架物理擦除）
- 触点一：价格/库存异动审计埋点（price_sync / stock_alert）
"""

import json

from app.logger import setup_logger
from app.models.content_change_history import (
    ChangeAction,
    ChangeEntityType,
    SyncSource,
    WriteResult,
)
from app.models.youzan_webhook_event import (
    YouzanWebhookBusinessType,
    YouzanWebhookStatus,
)
from app.repository.content_change_history_repo import ContentChangeHistoryRepo
from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.repository.youzan_webhook_event_repo import YouzanWebhookEventRepo
from app.service.youzan.audit_helper import mark_audit
from app.service.observability import (
    ContentChangeLogger,
    build_product_change_summary,
)
from app.utils import now_str

logger = setup_logger()


# 知识库常见成分特征标签（用于 RAG 搜索词索引增强）
async def handle_item_event(
    db,
    youzan_client,
    knowledge_retriever,
    event_type: str,
    msg_obj: dict,
    updated_at_str: str,
    msg_id: str = "",
    audit_repo: YouzanWebhookEventRepo | None = None,
    audit_id: int | None = None,
) -> None:
    """
    处理有赞商品系统事件。

    参数：
        db: aiosqlite 数据库连接
        youzan_client: 共享 YouzanClient 单例（避免并发刷新 token 竞态）
        knowledge_retriever: 知识检索器（用于 RAG 向量同步）
        event_type: 事件类型（如 item_ItemAdd）
        msg_obj: 有赞 Webhook msg 字段解码后的字典
        updated_at_str: 事件时间字符串
    """
    from app.repository.youzan_repo import YouzanProductRepo
    from app.repository.analytics_repo import AnalyticsRepo

    item_id = msg_obj.get("item_id", 0)
    # 始终解析内层 data：ITEM_STATE 的 is_display 等状态字段依赖它，
    # 不能因 item_id 已由上游解析而跳过，否则会丢失下架状态判定
    _inner_data: dict = {}
    _raw_data = msg_obj.get("data", "{}")
    try:
        _parsed = json.loads(_raw_data) if isinstance(_raw_data, str) else _raw_data
        _inner_data = _parsed if isinstance(_parsed, dict) else {}
    except Exception as exc:
        logger.warning("解析有赞事件内层 data 失败: %s", exc)
    if not item_id:
        item_id = _inner_data.get("item_id", 0)
    if not item_id:
        logger.warning("有赞商品事件缺少 item_id")
        await mark_audit(
            audit_repo,
            audit_id,
            YouzanWebhookStatus.SKIPPED,
            "item_missing_item_id",
            business_type=YouzanWebhookBusinessType.ITEM,
            error_type="missing_item_id",
        )
        return

    logger.info("开始处理有赞商品 Webhook 事件 [%s]: item_id=%s", event_type, item_id)
    await mark_audit(
        audit_repo,
        audit_id,
        YouzanWebhookStatus.PROCESSING,
        "item_api_fetch",
        business_type=YouzanWebhookBusinessType.ITEM,
        business_key=str(item_id),
    )

    product_repo = YouzanProductRepo(db)
    knowledge_product_repo = KnowledgeProductRepo(db)
    analytics_repo = AnalyticsRepo(db)
    history_logger = ContentChangeLogger(ContentChangeHistoryRepo(db))

    try:
        old_price, old_stock = -1, -1
        local_product = await product_repo.get_by_id(item_id)
        if local_product:
            old_price = local_product["price_fen"]
            old_stock = local_product["stock"]

        raw_product = await youzan_client.get_product(item_id)

        if isinstance(raw_product, dict) and raw_product.get("gw_err_resp"):
            logger.error(
                "商品事件 API 拒绝: item_id=%s err=%s",
                item_id,
                raw_product["gw_err_resp"],
            )
            await mark_audit(
                audit_repo,
                audit_id,
                YouzanWebhookStatus.FAILED,
                "item_api_rejected",
                business_type=YouzanWebhookBusinessType.ITEM,
                error_type="gw_err_resp",
                error_message=str(raw_product["gw_err_resp"]),
                business_key=str(item_id),
            )
            await history_logger.log_failed(
                entity_type=ChangeEntityType.PRODUCT,
                entity_key=str(item_id),
                category="product",
                title=f"商品 {item_id}",
                source=SyncSource.YOUZAN_WEBHOOK,
                source_ref=str(item_id),
                webhook_msg_id=msg_id,
                action=ChangeAction.UPSERT,
                error_type="gw_err_resp",
                error_message=str(raw_product["gw_err_resp"]),
            )
            return
        from app.service.youzan.product_sync import (
            parse_product_from_api,
            build_tags_str,
            sync_product_to_db,
            sync_product_to_rag,
        )

        parsed = parse_product_from_api(raw_product, item_id)
        if parsed is None:
            logger.error("商品事件响应结构异常: item_id=%s", item_id)
            await mark_audit(
                audit_repo,
                audit_id,
                YouzanWebhookStatus.FAILED,
                "item_api_bad_response",
                business_type=YouzanWebhookBusinessType.ITEM,
                error_type="missing_item",
                business_key=str(item_id),
            )
            await history_logger.log_failed(
                entity_type=ChangeEntityType.PRODUCT,
                entity_key=str(item_id),
                category="product",
                title=f"商品 {item_id}",
                source=SyncSource.YOUZAN_WEBHOOK,
                source_ref=str(item_id),
                webhook_msg_id=msg_id,
                action=ChangeAction.UPSERT,
                error_type="missing_item",
                error_message="商品接口响应缺少 item",
            )
            return

        title = parsed["title"]
        is_active = (
            0 if ("instock" in event_type or event_type.endswith("Instock")) else 1
        )
        if event_type == "ITEM_STATE" and "is_display" in _inner_data:
            is_active = 1 if _inner_data.get("is_display") else 0
        else:
            _is_explicit_state_event = (
                "instock" in event_type.lower()
                or "onsale" in event_type.lower()
                or event_type == "ITEM_STATE"
            )
            if not _is_explicit_state_event and local_product is not None:
                is_active = local_product["is_active"]

        status_lbl = "在售" if is_active == 1 else "下架"
        tags_str = build_tags_str(parsed, status_lbl)

        product_result = await sync_product_to_db(
            product_repo,
            parsed,
            is_active,
            updated_at_str,
            tags_str,
            SyncSource.YOUZAN_WEBHOOK,
            str(item_id),
        )
        knowledge_result = await sync_product_to_rag(
            knowledge_product_repo,
            knowledge_retriever.embedding_searcher,
            parsed,
            is_active,
            tags_str,
            status_lbl,
            updated_at_str,
            SyncSource.YOUZAN_WEBHOOK,
            str(item_id),
        )
        if knowledge_result == WriteResult.FAILED:
            raise RuntimeError(f"商品向量同步失败: item_id={item_id}")

        price_fen = parsed["price_fen"]
        stock = parsed["stock"]
        event_time = now_str()
        if old_price != -1 and old_price != price_fen:
            await analytics_repo.add_event(
                session_id=None,
                buyer_id=None,
                event_type="price_sync",
                event_source="webhook_youzan",
                ref_id=str(item_id),
                meta_data=json.dumps(
                    {
                        "product_title": title,
                        "old_price_fen": old_price,
                        "new_price_fen": price_fen,
                    },
                    ensure_ascii=False,
                ),
                created_at=event_time,
            )
            logger.info(
                "已成功记录商品价格调价审计埋点: title=%s, old=%d, new=%d",
                title,
                old_price,
                price_fen,
            )

        if old_stock != -1 and old_stock != stock:
            await analytics_repo.add_event(
                session_id=None,
                buyer_id=None,
                event_type="stock_alert",
                event_source="webhook_youzan",
                ref_id=str(item_id),
                meta_data=json.dumps(
                    {
                        "product_title": title,
                        "old_stock": old_stock,
                        "new_stock": stock,
                    },
                    ensure_ascii=False,
                ),
                created_at=event_time,
            )
            logger.info(
                "已成功记录商品库存预警审计埋点: title=%s, old_stock=%d, new_stock=%d",
                title,
                old_stock,
                stock,
            )
        if (
            product_result == WriteResult.APPLIED
            or knowledge_result == WriteResult.APPLIED
        ):
            await history_logger.log_success(
                entity_type=ChangeEntityType.PRODUCT,
                entity_key=str(item_id),
                category="product",
                title=title,
                source=SyncSource.YOUZAN_WEBHOOK,
                source_ref=str(item_id),
                webhook_msg_id=msg_id,
                action=ChangeAction.UPSERT
                if is_active == 1
                else ChangeAction.DEACTIVATE,
                change_summary=build_product_change_summary(
                    item_id=item_id,
                    title=title,
                    alias=parsed["alias"],
                    price_fen=price_fen,
                    stock=stock,
                    is_active=is_active,
                    tags=tags_str,
                    product_result=product_result,
                    knowledge_result=knowledge_result,
                    updated_at=updated_at_str,
                    old_price_fen=old_price
                    if old_price != -1 and old_price != price_fen
                    else None,
                    old_stock=old_stock
                    if old_stock != -1 and old_stock != stock
                    else None,
                ),
                occurred_at=updated_at_str,
            )
        await mark_audit(
            audit_repo,
            audit_id,
            YouzanWebhookStatus.PROCESSED,
            "item_processed",
            business_type=YouzanWebhookBusinessType.ITEM,
            business_key=str(item_id),
        )

    except Exception as exc:
        logger.error("处理有赞商品系统事件失败: item_id=%s err=%s", item_id, exc)
        await history_logger.log_failed(
            entity_type=ChangeEntityType.PRODUCT,
            entity_key=str(item_id),
            category="product",
            title=f"商品 {item_id}",
            source=SyncSource.YOUZAN_WEBHOOK,
            source_ref=str(item_id),
            webhook_msg_id=msg_id,
            action=ChangeAction.UPSERT,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        await mark_audit(
            audit_repo,
            audit_id,
            YouzanWebhookStatus.FAILED,
            "item_failed",
            business_type=YouzanWebhookBusinessType.ITEM,
            error_type=type(exc).__name__,
            error_message=str(exc),
            business_key=str(item_id),
        )
        raise
