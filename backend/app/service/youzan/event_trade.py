"""
有赞交易事件处理器。

处理有赞 Webhook 推送的交易订单状态变更事件（trade_*）：
- 物理宽表 Upsert（orders）
- 触点二：订单履约生命周期状态变更埋点（order_state_change）
- 触点四：24 小时 AI 导购 ROI 付款归因埋点（order_conversion）
"""

import json

from app.logger import setup_logger
from app.models.order import YouzanOrderData
from app.models.youzan_webhook_event import (
    YouzanWebhookBusinessType,
    YouzanWebhookStatus,
)
from app.repository.youzan_webhook_event_repo import YouzanWebhookEventRepo
from app.service.youzan.audit_helper import mark_audit
from app.service.youzan.order_parser import parse_youzan_order_response
from app.utils import now_str

logger = setup_logger()


async def handle_trade_event(
    db,
    youzan_client,
    event_type: str,
    msg_obj: dict,
    updated_at_str: str,
    audit_repo: YouzanWebhookEventRepo | None = None,
    audit_id: int | None = None,
) -> None:
    """
    处理有赞交易系统事件。

    参数：
        db: aiosqlite 数据库连接
        youzan_client: 共享 YouzanClient 单例（避免并发刷新 token 竞态）
        event_type: 事件类型（如 trade_TradeBuyerPay）
        msg_obj: 有赞 Webhook msg 字段解码后的字典
        updated_at_str: 事件时间字符串
    """
    from app.repository.youzan_repo import YouzanOrderRepo, YouzanProductRepo
    from app.repository.analytics_repo import AnalyticsRepo

    tid = msg_obj.get("tid", "")
    if not tid:
        _foi = msg_obj.get("full_order_info", {})
        tid = _foi.get("order_info", {}).get("tid", "")
    if not tid:
        await mark_audit(
            audit_repo,
            audit_id,
            YouzanWebhookStatus.SKIPPED,
            "trade_missing_tid",
            business_type=YouzanWebhookBusinessType.TRADE,
            error_type="missing_tid",
        )
        logger.warning("有赞交易事件缺少 tid")
        return

    logger.info("开始处理有赞交易 Webhook 事件 [%s]: tid=%s", event_type, tid)
    await mark_audit(
        audit_repo,
        audit_id,
        YouzanWebhookStatus.PROCESSING,
        "trade_api_fetch",
        business_type=YouzanWebhookBusinessType.TRADE,
        business_key=tid,
    )

    order_repo = YouzanOrderRepo(db)
    product_repo = YouzanProductRepo(db)
    analytics_repo = AnalyticsRepo(db)

    try:
        old_status = "NONE"
        local_order = await order_repo.get_by_order_no(tid)
        if local_order:
            old_status = local_order["status"]

        raw_order = await youzan_client.get_order(tid)
        parsed = parse_youzan_order_response(raw_order)
        if parsed is None:
            logger.warning(
                "有赞 trade.get 响应缺少 full_order_info，跳过 DB 写入: tid=%s", tid
            )
            await mark_audit(
                audit_repo,
                audit_id,
                YouzanWebhookStatus.FAILED,
                "trade_api_bad_response",
                business_type=YouzanWebhookBusinessType.TRADE,
                error_type="missing_full_order_info",
                business_key=tid,
            )
            return

        await order_repo.upsert_order(
            YouzanOrderData(
                order_no=tid,
                buyer_id=parsed.buyer_id,
                status=parsed.status,
                amount_fen=parsed.payment_fen,
                logistics_no=local_order["logistics_no"] if local_order else "",
                logistics_status=local_order["logistics_status"] if local_order else "",
                product_titles=parsed.product_titles,
                total_quantity=parsed.total_qty,
                pay_time=parsed.order_info.get("pay_time", ""),
                consign_time=parsed.order_info.get("consign_time", ""),
                pay_type_str=parsed.order_info.get("pay_type_str", ""),
                express_type=int(parsed.order_info.get("express_type", 0)),
                refund_state=int(parsed.order_info.get("refund_state", 0)),
                post_fee_fen=parsed.post_fee_fen,
                discount_fen=parsed.discount_fen,
                delivery_province=parsed.addr_info.get("delivery_province", ""),
                delivery_city=parsed.addr_info.get("delivery_city", ""),
                delivery_district=parsed.addr_info.get("delivery_district", ""),
                delivery_time=parsed.addr_info.get("delivery_start_time", ""),
                outer_user_id=parsed.outer_user_id,
                order_items_json=json.dumps(parsed.items_detail, ensure_ascii=False),
                created_at=parsed.order_info.get("created", ""),
                updated_at=updated_at_str,
            )
        )

        if old_status != parsed.status:
            await analytics_repo.add_event(
                session_id=None,
                buyer_id=parsed.buyer_id,
                event_type="order_state_change",
                event_source="webhook_youzan",
                ref_id=tid,
                meta_data=json.dumps(
                    {"old_status": old_status, "new_status": parsed.status},
                    ensure_ascii=False,
                ),
                created_at=now_str(),
            )
            logger.info(
                "已成功记录订单履约时效埋点: tid=%s, old=%s, new=%s",
                tid,
                old_status,
                parsed.status,
            )

        is_payment_event = event_type == "trade_TradeBuyerPay" or (
            old_status in ("NONE", "WAIT_BUYER_PAY")
            and parsed.status
            in ("WAIT_SELLER_SEND_GOODS", "TRADE_PAID", "TRADE_SUCCESS")
        )
        if is_payment_event:
            logger.info(
                "触发 24 小时 AI 导购业绩付款归因校验: buyer=%s", parsed.buyer_id
            )
            for item in parsed.order_items:
                item_id = item.get("item_id", 0)
                if not item_id:
                    continue
                product = await product_repo.get_by_id(item_id)
                if not product:
                    continue
                alias = product["alias"]
                ai_session_id = await analytics_repo.check_ai_recommend_for_conversion(
                    parsed.buyer_id, alias, lookback_hours=24
                )
                if ai_session_id:
                    await analytics_repo.add_event(
                        session_id=ai_session_id,
                        buyer_id=parsed.buyer_id,
                        event_type="order_conversion",
                        event_source="webhook_youzan",
                        ref_id=tid,
                        meta_data=json.dumps(
                            {
                                "product_title": item.get("title", ""),
                                "product_alias": alias,
                                "amount_fen": int(float(item.get("payment", 0)) * 100),
                                "lookback": "24_hours",
                            },
                            ensure_ascii=False,
                        ),
                        created_at=now_str(),
                    )
                    logger.info(
                        "🎉 完美！AI 导购业绩归因匹配成功！已为 Dashboard 记账绩效: session_id=%s, buyer_id=%s, gmv_fen=%s",
                        ai_session_id,
                        parsed.buyer_id,
                        item.get("payment"),
                    )
        await mark_audit(
            audit_repo,
            audit_id,
            YouzanWebhookStatus.PROCESSED,
            "trade_processed",
            business_type=YouzanWebhookBusinessType.TRADE,
            business_key=tid,
        )

    except Exception as exc:
        logger.error("处理有赞交易系统事件失败: tid=%s err=%s", tid, exc)
        await mark_audit(
            audit_repo,
            audit_id,
            YouzanWebhookStatus.FAILED,
            "trade_failed",
            business_type=YouzanWebhookBusinessType.TRADE,
            error_type=type(exc).__name__,
            error_message=str(exc),
            business_key=tid,
        )
