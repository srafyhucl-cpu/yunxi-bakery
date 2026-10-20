"""店员快捷开单服务：会员/商品查询与快捷开单创建。

创建链路只支持两种支付语义：
- stored_value_direct：建单、扣储值、置为已支付，任一步失败整单回滚；
- wechat_share_card：只建待支付订单，返回小程序订单详情分享路径。
同一 requestId 由 staff_quick_order_requests 占位，重复提交不重复建单或扣款。
"""

import json
import re
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from app.logger import setup_logger
from app.models.customer_master import CustomerIdentityType
from app.models.order import Order
from app.models.staff import StaffPrincipal
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.order_repo import OrderRepo
from app.repository.staff_quick_order_repo import StaffQuickOrderRequestRepo
from app.repository.staff_repo import StaffAuditRepo, StaffRepo
from app.repository.youzan_order_repo import YouzanOrderRepo
from app.service.catalog.application import CatalogApplicationService
from app.service.order.payment_state import loads_payment, status_value
from app.service.staff_auth import STAFF_TENANT_ID, mask_phone
from app.utils import fen_to_yuan_str, yuan_to_fen

if TYPE_CHECKING:
    from app.service.order import OrderApplicationService
    from app.service.stored_value import StoredValueService

logger = setup_logger()

QUICK_ORDER_MEMBER_ORDER_LIMIT = 10
QUICK_ORDER_PRODUCT_DEFAULT_LIMIT = 20
QUICK_ORDER_PRODUCT_MAX_LIMIT = 50

MODE_STORED_VALUE_DIRECT = "stored_value_direct"
MODE_WECHAT_SHARE_CARD = "wechat_share_card"
QUICK_ORDER_MODES = (MODE_STORED_VALUE_DIRECT, MODE_WECHAT_SHARE_CARD)
QUICK_ORDER_PICKUP = "pickup"
QUICK_ORDER_DEFAULT_RECEIVER_NAME = "会员"
QUICK_ORDER_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
QUICK_ORDER_DEFAULT_EXPECT_MINUTES = 30
QUICK_ORDER_RECEIPT_TITLE = "芸熙烘焙 快捷开单"
QUICK_ORDER_SHARE_PATH_TEMPLATE = "/pages/order-detail/index?id={order_id}"
BOARD_PAYMENT_STATUS_TEXT = {
    "paid": "已支付",
    "unpaid": "待支付",
    "partial": "部分支付",
    "expired": "已过期",
}
BEIJING_TIME_ZONE = ZoneInfo("Asia/Shanghai")
EXPECT_TIME_FORMAT = "%Y-%m-%d %H:%M"


class StaffQuickOrderConflict(ValueError):
    """同一 requestId 正在处理中，API 层映射为 409。"""


class StaffQuickOrderService:
    """为店员快捷开单提供会员、商品查询与建单能力。"""

    def __init__(
        self,
        customer_repo: CustomerMasterRepo | None = None,
        member_balance_repo: MemberBalanceRepo | None = None,
        youzan_order_repo: YouzanOrderRepo | None = None,
        catalog_service: CatalogApplicationService | None = None,
        audit_repo: StaffRepo | StaffAuditRepo | None = None,
        order_service: "OrderApplicationService | None" = None,
        stored_value_service: "StoredValueService | None" = None,
        order_repo: OrderRepo | None = None,
        request_repo: StaffQuickOrderRequestRepo | None = None,
        staff_audit_repo: StaffRepo | StaffAuditRepo | None = None,
    ) -> None:
        # 启动期不读取数据库连接；未注入时由 db_session_scope 的 ContextVar 解析。
        self._customer_repo = customer_repo or CustomerMasterRepo(None)
        self._member_balance_repo = member_balance_repo or MemberBalanceRepo(None)
        self._youzan_order_repo = youzan_order_repo or YouzanOrderRepo(None)
        self._catalog_service = catalog_service
        self._order_service = order_service
        self._stored_value_service = stored_value_service
        self._order_repo = order_repo or OrderRepo(None)
        self._request_repo = request_repo or StaffQuickOrderRequestRepo(None)
        # staff_audit_repo 为 Stage 3C2A 显式命名；audit_repo 保留兼容旧装配。
        self._audit_repo = staff_audit_repo or audit_repo or StaffAuditRepo(None)

    async def lookup_member(
        self,
        phone: str,
        staff: StaffPrincipal,
        *,
        audit: bool = True,
    ) -> dict:
        """按手机号查询会员、储值拆分与最近有赞历史订单。"""
        clean_phone = self._normalize_phone(phone)
        phone_link = await self._customer_repo.get_identity_by_value(
            STAFF_TENANT_ID,
            CustomerIdentityType.PHONE.value,
            clean_phone,
        )
        customer = None
        if phone_link is not None:
            customer = await self._customer_repo.get_master(phone_link.customer_id)
        if customer is None:
            matches = await self._customer_repo.get_by_phone(
                STAFF_TENANT_ID, clean_phone
            )
            customer = matches[0] if matches else None
        if customer is None:
            raise ValueError("未找到该会员")

        openid = await self._resolve_miniapp_openid(customer.id)
        if not openid:
            raise ValueError("会员尚未绑定小程序")

        balance = await self._member_balance_repo.get_by_mobile(clean_phone) or {}
        stored_value_fen = int(balance.get("stored_value_fen", 0) or 0)
        principal_fen = int(balance.get("principal_fen", stored_value_fen) or 0)
        bonus_fen = int(balance.get("bonus_fen", 0) or 0)
        points = int(balance.get("points", 0) or 0)
        card_alias = str(balance.get("card_alias", "") or "")
        yz_open_id = str(balance.get("yz_open_id", "") or "").strip()

        order_rows = await self._youzan_order_repo.list_recent_for_identity(
            phone=clean_phone,
            yz_open_id=yz_open_id,
            limit=QUICK_ORDER_MEMBER_ORDER_LIMIT,
        )
        history_orders = [_format_history_order(row) for row in order_rows]

        if audit:
            await self._audit_repo.record_audit(
                staff.id,
                "lookup_member",
                target_type="customer",
                target_id=customer.id,
                detail_json=json.dumps(
                    {"phone": mask_phone(clean_phone)}, ensure_ascii=False
                ),
            )
        return {
            "customerId": customer.id,
            "mobile": clean_phone,
            "userId": f"wx_{openid}",
            "displayName": str(
                customer.display_name or balance.get("display_name", "") or ""
            ),
            "isMember": bool(balance.get("is_member", 0)),
            "storedValueFen": stored_value_fen,
            "principalFen": principal_fen,
            "bonusFen": bonus_fen,
            "points": points,
            "cardAlias": card_alias,
            "historyOrders": history_orders,
        }

    async def list_products(
        self,
        keyword: str,
        limit: int = QUICK_ORDER_PRODUCT_DEFAULT_LIMIT,
        *,
        staff: StaffPrincipal,
    ) -> list[dict]:
        """按关键词返回快捷开单所需的最小商品字段。"""
        if self._catalog_service is None:
            raise ValueError("商品目录服务未就绪")
        normalized_keyword = str(keyword or "").strip()
        safe_limit = max(1, min(int(limit), QUICK_ORDER_PRODUCT_MAX_LIMIT))
        products = await self._catalog_service.list_products(
            keyword=normalized_keyword,
            limit=safe_limit,
        )
        items = [
            {
                "productId": str(product.get("id", "")),
                "title": str(product.get("title", "")),
                "priceFen": int(product.get("priceFen", 0) or 0),
                "stock": int(product.get("stock", 0) or 0),
                "isPurchasable": bool(product.get("isPurchasable", False)),
                "imageUrl": str(product.get("imageUrl", "") or ""),
            }
            for product in products
        ]
        await self._audit_repo.record_audit(
            staff.id,
            "list_products",
            target_type="catalog",
            target_id="",
            detail_json=json.dumps(
                {"keywordLength": len(normalized_keyword), "limit": safe_limit},
                ensure_ascii=False,
            ),
        )
        return items

    async def create_quick_order(
        self,
        staff: StaffPrincipal,
        payload: dict,
    ) -> dict:
        """按 requestId 幂等创建店员快捷开单。"""
        normalized = self._normalize_create_payload(payload)
        request_id = normalized["requestId"]
        mode = normalized["mode"]

        reserved, existing = await self._request_repo.reserve(
            request_id,
            staff.id,
            mode,
        )
        if not reserved:
            return await self._resolve_replayed_request(mode, existing, staff.id)

        order_id = ""
        try:
            # 建单内部不再重复写 lookup_member 审计，只保留开单审计。
            member = await self.lookup_member(
                normalized["phone"],
                staff,
                audit=False,
            )
            order_payload = self._build_order_payload(member, normalized)
            # 外层事务覆盖建单、扣储值、请求完成与审计：任一步失败整单回滚。
            async with self._order_repo.transaction():
                created = await self._require_order_service().create_order(
                    order_payload,
                    user_id=member["userId"],
                )
                order_id = str(created["orderId"])
                if mode == MODE_STORED_VALUE_DIRECT:
                    await self._require_stored_value_service().pay_order_with_balance(
                        order_id,
                        user_id=member["userId"],
                    )
                order = await self._order_repo.get_order(order_id)
                if order is None:
                    raise ValueError("订单创建后未能读回")
                balance_fen = 0
                if mode == MODE_STORED_VALUE_DIRECT:
                    balance_fen = await self._read_balance_fen(member["userId"])
                await self._audit_repo.record_audit(
                    staff.id,
                    "quick_order_create",
                    target_type="order",
                    target_id=order_id,
                    detail_json=json.dumps(
                        {
                            "mode": mode,
                            "amountFen": int(created.get("totalFen", 0) or 0),
                            "requestId": request_id,
                        },
                        ensure_ascii=False,
                    ),
                )
                completed = await self._request_repo.complete(request_id, order_id)
                if not completed:
                    # 请求行已不是 pending 时不得提交订单与扣款，交由外层整体回滚。
                    raise ValueError("开单请求状态更新冲突，请重新发起")
            return self._build_success_response(order, mode, balance_fen)
        except Exception as exc:
            # 失败标记必须尝试落库后再抛出；标记写入失败不得覆盖原始业务异常。
            try:
                await self._request_repo.fail(request_id, str(exc))
            except Exception as mark_exc:
                logger.error(
                    "店员快捷开单失败标记写入失败 request_id=%s err=%s",
                    request_id,
                    mark_exc,
                )
            logger.error(
                "店员快捷开单失败 staff_id=%s request_id=%s mode=%s order_id=%s err=%s",
                staff.id,
                request_id,
                mode,
                order_id,
                exc,
            )
            raise

    async def _resolve_replayed_request(
        self,
        mode: str,
        existing: dict | None,
        staff_id: str,
    ) -> dict:
        """处理未抢到 requestId 的重复提交：completed 幂等回放，其余按状态报错。"""
        if existing is None:
            raise StaffQuickOrderConflict("订单正在处理，请勿重复提交")
        if str(existing.get("staff_id", "")) != staff_id:
            raise StaffQuickOrderConflict("requestId 已被其他店员占用，请重新发起")
        status = str(existing.get("status", ""))
        if status == "completed":
            return await self._rebuild_completed_response(mode, existing)
        if status == "pending":
            raise StaffQuickOrderConflict("订单正在处理，请勿重复提交")
        raise ValueError("上次开单失败，请重新发起")

    async def _rebuild_completed_response(self, mode: str, existing: dict) -> dict:
        """按既有 completed 记录重建响应，不再建单或扣款。"""
        order_id = str(existing.get("order_id", "") or "")
        if not order_id:
            raise ValueError("订单记录缺少订单号")
        order = await self._order_repo.get_order(order_id)
        if order is None:
            raise ValueError("订单不存在")
        record_mode = str(existing.get("mode", "") or mode)
        balance_fen = 0
        if record_mode == MODE_STORED_VALUE_DIRECT:
            balance_fen = await self._read_balance_fen(order.user_id)
        return self._build_success_response(order, record_mode, balance_fen)

    def _build_success_response(
        self,
        order: Order,
        mode: str,
        balance_fen: int,
    ) -> dict:
        """构造店员可直接展示/复制的开单结果。"""
        payment = loads_payment(order.payment)
        receipt_text = build_receipt_text(order, mode, balance_fen)
        response = {
            "orderId": order.id,
            "status": status_value(order),
            "paymentStatus": str(payment.get("status", "unpaid")),
            "receiptText": receipt_text,
        }
        if mode == MODE_STORED_VALUE_DIRECT:
            response["balanceFen"] = balance_fen
            return response
        share_path = QUICK_ORDER_SHARE_PATH_TEMPLATE.format(order_id=order.id)
        response["sharePath"] = share_path
        response["shareText"] = f"您的订单已创建，请打开小程序完成支付：{share_path}"
        return response

    async def _read_balance_fen(self, user_id: str) -> int:
        """读取会员当前剩余储值余额，用于回执与幂等回放。"""
        balance = await self._require_stored_value_service().get_user_balance(user_id)
        return int(balance.get("balanceFen", 0) or 0)

    def _normalize_create_payload(self, payload: dict) -> dict:
        """校验并规范化开单入参，只接受到店自提。"""
        if not isinstance(payload, dict):
            raise ValueError("开单参数无效")
        request_id = str(payload.get("requestId", "") or "").strip()
        if not request_id:
            raise ValueError("requestId 不能为空")
        if not QUICK_ORDER_REQUEST_ID_PATTERN.fullmatch(request_id):
            raise ValueError("requestId 必须为 8-64 位字母、数字、下划线或连字符")
        mode = str(payload.get("mode", "") or "").strip()
        if mode not in QUICK_ORDER_MODES:
            raise ValueError("不支持的快捷开单支付方式")
        phone = self._normalize_phone(str(payload.get("phone", "") or ""))
        items = payload.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError("订单商品不能为空")
        fulfillment_method = str(
            payload.get(
                "fulfillmentMethod",
                payload.get("deliveryType", QUICK_ORDER_PICKUP),
            )
            or QUICK_ORDER_PICKUP
        ).strip()
        if fulfillment_method != QUICK_ORDER_PICKUP:
            raise ValueError("本轮快捷开单仅支持到店自提")
        expect_time = str(payload.get("expectTime", "") or "").strip()
        if not expect_time:
            expect_time = self._default_expect_time()
        return {
            "requestId": request_id,
            "mode": mode,
            "phone": phone,
            "items": items,
            "expectTime": expect_time,
            "remark": str(payload.get("remark", "") or "").strip(),
        }

    def _build_order_payload(self, member: dict, normalized: dict) -> dict:
        """把会员与开单入参转换为订单创建合同，items 原样传递。"""
        display_name = str(member.get("displayName", "") or "").strip()
        return {
            "items": normalized["items"],
            "receiverName": display_name or QUICK_ORDER_DEFAULT_RECEIVER_NAME,
            "receiverPhone": member["mobile"],
            "fulfillmentMethod": QUICK_ORDER_PICKUP,
            "deliveryType": QUICK_ORDER_PICKUP,
            "expectTime": normalized["expectTime"],
            "remark": normalized["remark"],
        }

    def _require_order_service(self) -> "OrderApplicationService":
        if self._order_service is None:
            raise ValueError("订单服务未就绪")
        return self._order_service

    def _require_stored_value_service(self) -> "StoredValueService":
        if self._stored_value_service is None:
            raise ValueError("储值服务未就绪")
        return self._stored_value_service

    def _default_expect_time(self) -> str:
        """缺省预约时间为北京时间当前时间 + 30 分钟。"""
        return (
            datetime.now(BEIJING_TIME_ZONE)
            + timedelta(minutes=QUICK_ORDER_DEFAULT_EXPECT_MINUTES)
        ).strftime(EXPECT_TIME_FORMAT)

    async def _resolve_miniapp_openid(self, customer_id: str) -> str:
        """从客户身份链接中取出已绑定的小程序 openid。"""
        links = await self._customer_repo.list_identity_links(customer_id)
        for link in links:
            if link.identity_type != CustomerIdentityType.MINIAPP_OPENID.value:
                continue
            value = str(link.identity_value or "").strip()
            if value:
                return value
        return ""

    @staticmethod
    def _normalize_phone(phone: str) -> str:
        value = str(phone or "").strip()
        if len(value) != 11 or not value.isdigit() or not value.startswith("1"):
            raise ValueError("请输入有效的11位手机号")
        return value


def build_receipt_text(order: Order, mode: str, balance_fen: int = 0) -> str:
    """生成店员可打印/复制的订单回执，不暴露内部账本字段。"""
    payment = loads_payment(order.payment)
    lines = [
        QUICK_ORDER_RECEIPT_TITLE,
        f"订单号：{order.id}",
        "商品明细：",
    ]
    for item in _load_order_products(order.products):
        title = str(item.get("title", "") or item.get("product_id", "") or "")
        quantity = int(item.get("quantity", 0) or 0)
        price_fen = int(item.get("price_fen", 0) or 0)
        lines.append(
            f"- {title} x{quantity}  {fen_to_yuan_str(price_fen * quantity)}元"
        )
    total_fen = yuan_to_fen(order.total_amount)
    lines.append(f"合计：{fen_to_yuan_str(total_fen)}元")
    if mode == MODE_STORED_VALUE_DIRECT:
        lines.append("支付方式：储值余额")
    else:
        lines.append("支付方式：微信分享待付")
    payment_status = str(payment.get("status", "unpaid"))
    lines.append(
        "支付状态：" + BOARD_PAYMENT_STATUS_TEXT.get(payment_status, payment_status)
    )
    if mode == MODE_STORED_VALUE_DIRECT:
        paid_fen = int(payment.get("balanceFen", 0) or 0)
        lines.append(f"余额支付：{fen_to_yuan_str(paid_fen)}元")
        lines.append(f"剩余余额：{fen_to_yuan_str(balance_fen)}元")
    return "\n".join(lines)


def _load_order_products(raw: str) -> list[dict]:
    """解析订单商品 JSON；历史脏数据只记录告警并按空明细展示。"""
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        logger.error("订单商品 JSON 解析失败: %s", exc)
        return []
    if not isinstance(value, list):
        logger.error("订单商品 JSON 不是数组: %s", type(value).__name__)
        return []
    return [item for item in value if isinstance(item, dict)]


def _format_history_order(row: dict) -> dict:
    """把有赞订单宽表行转换为店员可读的历史订单摘要。"""
    return {
        "orderNo": str(row.get("order_no", "") or ""),
        "status": str(row.get("status", "") or ""),
        "amountFen": int(row.get("amount_fen", 0) or 0),
        "productTitles": str(row.get("product_titles", "") or ""),
        "totalQuantity": int(row.get("total_quantity", 0) or 0),
        "payTime": str(row.get("pay_time", "") or ""),
        "createdAt": str(row.get("created_at", "") or ""),
    }


__all__ = [
    "MODE_STORED_VALUE_DIRECT",
    "MODE_WECHAT_SHARE_CARD",
    "StaffQuickOrderConflict",
    "StaffQuickOrderService",
    "build_receipt_text",
]
