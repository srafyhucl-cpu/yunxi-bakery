"""
Function Calling 工具实现：订单与物流查询。

提供 get_order_info（本地短路 + 有赞实时）和 get_logistics_info（物流轨迹查询 + 宽表反写）。
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from app.logger import setup_logger
from app.models.order import YouzanOrderData
from app.service.youzan.order_parser import parse_youzan_order_response

if TYPE_CHECKING:
    from app.service.knowledge_retriever import KnowledgeRetriever
    from app.service.youzan.client import YouzanClient

logger = setup_logger()

ORDER_OWNERSHIP_DENIAL_MESSAGE = "无法确认订单归属，请转人工客服"


async def get_order_info(
    knowledge_retriever: KnowledgeRetriever,
    order_no: str,
    youzan_client: YouzanClient | None = None,
    order_repo=None,
    config_repo=None,
    buyer_id: str | None = None,
    outer_user_id: str | None = None,
) -> str:
    """
    查询订单详细信息（内置已完成/已关闭订单状态机本地短路流控防线）。

    参数：
        youzan_client: 共享 YouzanClient 单例（由 ChatService 注入，避免并发竞态）
    """
    if order_repo is None:
        return json.dumps(
            {
                "order_no": order_no,
                "available": False,
                "message": "订单查询服务暂不可用",
            },
            ensure_ascii=False,
        )

    try:
        local_order = await _get_local_order(
            order_repo,
            order_no,
            buyer_id=buyer_id,
            outer_user_id=outer_user_id,
        )
        if local_order and local_order["status"] in ("TRADE_SUCCESS", "TRADE_CLOSED"):
            logger.info(
                "已完成/已关闭订单触发本地状态机短路秒回: order_no=%s", order_no
            )
            return json.dumps(
                {
                    "order_no": order_no,
                    "status": local_order["status"],
                    "amount_yuan": local_order["amount_fen"] / 100.0,
                    "product_titles": local_order["product_titles"],
                    "logistics_no": local_order["logistics_no"],
                    "logistics_status": local_order["logistics_status"],
                    "source": "local_short_circuit",
                },
                ensure_ascii=False,
            )

        if youzan_client is None:
            from app.service.youzan.client import YouzanClient as _YZC

            if config_repo is None:
                if _has_order_identity(buyer_id, outer_user_id) and local_order is None:
                    return _ownership_denied(order_no)
                return json.dumps(
                    {
                        "order_no": order_no,
                        "available": False,
                        "message": "订单查询服务暂不可用",
                    },
                    ensure_ascii=False,
                )
            youzan_client = _YZC(config_repo=config_repo)
        raw_order = await youzan_client.get_order(order_no)
        parsed = parse_youzan_order_response(raw_order)
        if parsed is None:
            return json.dumps(
                {
                    "order_no": order_no,
                    "available": False,
                    "message": "未找到此订单，请检查您的订单号或小程序绑定手机号是否输入正确",
                },
                ensure_ascii=False,
            )

        if _has_order_identity(buyer_id, outer_user_id) and not _matches_order_identity(
            parsed.buyer_id,
            parsed.outer_user_id,
            buyer_id=buyer_id,
            outer_user_id=outer_user_id,
        ):
            logger.warning("有赞订单身份不匹配，拒绝返回或缓存: order_no=%s", order_no)
            return _ownership_denied(order_no)

        await order_repo.upsert_order(
            YouzanOrderData(
                order_no=order_no,
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
                updated_at=parsed.order_info.get("update_time", "")
                or parsed.order_info.get("created", ""),
            )
        )

        return json.dumps(
            {
                "order_no": order_no,
                "status": parsed.status,
                "status_str": parsed.order_info.get("status_str", ""),
                "amount_yuan": parsed.payment_fen / 100.0,
                "post_fee_yuan": parsed.post_fee,
                "discount_yuan": parsed.discount_fen / 100.0,
                "product_titles": parsed.product_titles,
                "pay_time": parsed.order_info.get("pay_time", ""),
                "pay_type": parsed.order_info.get("pay_type_str", ""),
                "delivery_province": parsed.addr_info.get("delivery_province", ""),
                "delivery_city": parsed.addr_info.get("delivery_city", ""),
                "delivery_district": parsed.addr_info.get("delivery_district", ""),
                "delivery_time": parsed.addr_info.get("delivery_start_time", ""),
                "order_items": parsed.items_detail,
                "source": "youzan_live_api",
            },
            ensure_ascii=False,
        )

    except Exception as exc:
        logger.error("有赞订单查询失败: order_no=%s err=%s", order_no, exc)
        return json.dumps(
            {
                "order_no": order_no,
                "available": False,
                "message": "订单查询发生系统异常，请稍后再试或联系人工客服",
            },
            ensure_ascii=False,
        )


async def get_logistics_info(
    knowledge_retriever: KnowledgeRetriever,
    order_no: str,
    youzan_client: YouzanClient | None = None,
    order_repo=None,
    config_repo=None,
    buyer_id: str | None = None,
    outer_user_id: str | None = None,
) -> str:
    """
    查询物流配送进度并反写更新 orders 交易物理大宽表。

    参数：
        youzan_client: 共享 YouzanClient 单例（由 ChatService 注入，避免并发竞态）
    """
    if order_repo is None:
        return json.dumps(
            {
                "order_no": order_no,
                "available": False,
                "message": "物流查询服务暂不可用",
            },
            ensure_ascii=False,
        )

    try:
        local_order = await _get_local_order(
            order_repo,
            order_no,
            buyer_id=buyer_id,
            outer_user_id=outer_user_id,
        )
        if _has_order_identity(buyer_id, outer_user_id) and local_order is None:
            return _ownership_denied(order_no)

        if youzan_client is None:
            from app.service.youzan.client import YouzanClient as _YZC

            if config_repo is None:
                return json.dumps(
                    {
                        "order_no": order_no,
                        "available": False,
                        "message": "物流查询服务暂不可用",
                    },
                    ensure_ascii=False,
                )
            youzan_client = _YZC(config_repo=config_repo)
        raw_logistics = await youzan_client.get_logistics(order_no)

        express_data = (
            raw_logistics.get("data") or raw_logistics.get("response")
            if isinstance(raw_logistics, dict)
            else None
        )
        if not isinstance(express_data, dict):
            return json.dumps(
                {
                    "order_no": order_no,
                    "available": False,
                    "message": "未查询到物流派送信息，可能商家尚未发货",
                },
                ensure_ascii=False,
            )

        express_id = express_data.get("express_id", "")
        express_name = express_data.get("express_name", "")
        step_descs = [
            f"[{s.get('status_time', '')}] {s.get('status_desc', '')}"
            for s in express_data.get("transit_step_infos", [])
        ]

        if local_order:
            await order_repo.upsert_order(
                YouzanOrderData(
                    order_no=local_order["order_no"],
                    buyer_id=local_order["buyer_id"],
                    status=local_order["status"],
                    amount_fen=local_order["amount_fen"],
                    logistics_no=express_id,
                    logistics_status=step_descs[-1] if step_descs else "暂无轨迹",
                    product_titles=local_order["product_titles"],
                    total_quantity=local_order["total_quantity"],
                    pay_time=local_order.get("pay_time", ""),
                    consign_time=local_order.get("consign_time", ""),
                    pay_type_str=local_order.get("pay_type_str", ""),
                    express_type=local_order.get("express_type", 0),
                    refund_state=local_order.get("refund_state", 0),
                    post_fee_fen=local_order.get("post_fee_fen", 0),
                    discount_fen=local_order.get("discount_fen", 0),
                    delivery_province=local_order.get("delivery_province", ""),
                    delivery_city=local_order.get("delivery_city", ""),
                    delivery_district=local_order.get("delivery_district", ""),
                    delivery_time=local_order.get("delivery_time", ""),
                    outer_user_id=local_order.get("outer_user_id", ""),
                    order_items_json=local_order.get("order_items_json", "[]"),
                    created_at=local_order["created_at"],
                    updated_at=local_order["updated_at"],
                )
            )

        return json.dumps(
            {
                "order_no": order_no,
                "express_name": express_name,
                "express_id": express_id,
                "steps": step_descs[:5],
                "message": "查询成功",
            },
            ensure_ascii=False,
        )

    except Exception as exc:
        logger.error("有赞物流查询失败: order_no=%s err=%s", order_no, exc)
        return json.dumps(
            {
                "order_no": order_no,
                "available": False,
                "message": "物流查询发生异常，请稍后再试或联系人工客服获取配送进度",
            },
            ensure_ascii=False,
        )


async def _get_local_order(
    order_repo,
    order_no: str,
    *,
    buyer_id: str | None,
    outer_user_id: str | None,
) -> dict | None:
    if _has_order_identity(buyer_id, outer_user_id):
        return await order_repo.get_by_order_no_for_identity(
            order_no,
            buyer_id=buyer_id,
            outer_user_id=outer_user_id,
        )
    return await order_repo.get_by_order_no(order_no)


def _has_order_identity(
    buyer_id: str | None,
    outer_user_id: str | None,
) -> bool:
    return bool((buyer_id or "").strip() or (outer_user_id or "").strip())


def _matches_order_identity(
    actual_buyer_id: str,
    actual_outer_user_id: str,
    *,
    buyer_id: str | None,
    outer_user_id: str | None,
) -> bool:
    normalized_buyer_id = (buyer_id or "").strip()
    normalized_outer_user_id = (outer_user_id or "").strip()
    return bool(
        (normalized_buyer_id and actual_buyer_id == normalized_buyer_id)
        or (
            normalized_outer_user_id
            and actual_outer_user_id == normalized_outer_user_id
        )
    )


def _ownership_denied(order_no: str) -> str:
    return json.dumps(
        {
            "order_no": order_no,
            "available": False,
            "message": ORDER_OWNERSHIP_DENIAL_MESSAGE,
        },
        ensure_ascii=False,
    )
