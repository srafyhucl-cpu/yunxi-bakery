"""优惠券域应用服务门面。"""

from app.config import settings
from app.models.member import CouponStatus
from app.models.order import Order
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.order_repo import OrderRepo
from app.service.coupon.inventory import CouponInventoryService
from app.service.coupon.rules import calc_discount, is_coupon_available
from app.service.order.payment_state import (
    PAYMENT_STATUS_PAID,
    PAYMENT_STATUS_UNPAID,
    compute_remain_fen,
    loads_payment,
)


class CouponService:
    """优惠券域门面：查询/预览/应用/支付联动/退款。"""

    def __init__(
        self,
        template_repo: CouponTemplateRepo | None = None,
        inventory_repo: CouponInventoryRepo | None = None,
        customer_repo: CustomerMasterRepo | None = None,
        order_repo: OrderRepo | None = None,
        inventory_service: CouponInventoryService | None = None,
    ) -> None:
        self._template_repo = template_repo or CouponTemplateRepo(None)
        self._inventory_repo = inventory_repo or CouponInventoryRepo(None)
        self._customer_repo = customer_repo or CustomerMasterRepo(None)
        self._order_repo = order_repo or OrderRepo(None)
        # 券库存服务惰性解析：lifespan 装配期无 db_session_scope，禁止构造期访问 _db
        self._inventory_service = inventory_service

    @property
    def _inventory(self) -> CouponInventoryService:
        """惰性解析券库存服务（首次方法调用期按数据源构建）。"""
        if self._inventory_service is None:
            self._inventory_service = CouponInventoryService(self._order_repo._db)
        return self._inventory_service

    async def resolve_mobile(self, user_id: str) -> str:
        """把小程序用户标识解析为会员手机号。"""
        from app.service.stored_value.member import MemberBalanceService

        return await MemberBalanceService(
            customer_repo=self._customer_repo
        ).resolve_mobile(user_id)

    async def get_my_coupons(self, user_id: str) -> dict:
        """我的券列表（最新态 + 模板信息）。"""
        mobile = await self.resolve_mobile(user_id)
        rows = await self._inventory_repo.list_by_mobile(
            mobile, authority=settings.COUPON_AUTHORITY
        )
        template_ids = sorted(
            {
                str(row.get("template_id", "") or "")
                for row in rows
                if row.get("template_id")
            }
        )
        templates = await self._template_repo.list_by_ids(template_ids)
        template_map = {str(t["id"]): dict(t) for t in templates}
        coupons = []
        for row in rows:
            template = template_map.get(str(row.get("template_id", "") or ""), {})
            coupons.append(
                {
                    "couponId": row["coupon_id"],
                    "templateId": row.get("template_id", ""),
                    "title": row.get("title", ""),
                    "status": row.get("status", ""),
                    "valueFen": row.get("value_fen", 0),
                    "thresholdFen": int(template.get("threshold_fen", 0) or 0),
                    "deductedFen": row.get("deducted_fen", 0),
                    "validFrom": row.get("valid_from", ""),
                    "validUntil": row.get("valid_until", ""),
                    "orderNo": row.get("order_no", ""),
                }
            )
        return {"mobile": mobile, "coupons": coupons}

    async def redeem_preview(self, order_id: str, *, user_id: str) -> dict:
        """结算选券预览（可用券 + 每张可减金额 + 叠加校验结果）。"""
        order = await self._owned_order(order_id, user_id)
        payment = loads_payment(order.payment)
        payment_status = str(payment.get("status", PAYMENT_STATUS_UNPAID))
        if payment_status == PAYMENT_STATUS_PAID:
            raise ValueError("订单已支付")
        total_fen = self._total_fen(order)
        balance_fen = int(payment.get("balanceFen", 0) or 0)
        points_fen = int(payment.get("pointsFen", 0) or 0)
        if balance_fen > 0:
            # 余额已扣的真实 partial：与 apply_coupon 守卫一致，预览返回空可用券
            return {
                "orderId": order.id,
                "totalFen": total_fen,
                "balanceFen": balance_fen,
                "pointsFen": points_fen,
                "available": [],
                "remainFen": compute_remain_fen(total_fen, 0, balance_fen, points_fen),
            }
        mobile = await self.resolve_mobile(user_id)
        rows = await self._inventory_repo.list_by_mobile(
            mobile, authority=settings.COUPON_AUTHORITY
        )
        now = self._now_text()
        available = []
        for row in rows:
            if row.get("status") != CouponStatus.TAKE:
                continue
            template_row = await self._template_repo.get(
                str(row.get("template_id", ""))
            )
            template = dict(template_row) if template_row is not None else None
            if template is None:
                template = {
                    "id": row.get("template_id", ""),
                    "coupon_type": "",
                    "threshold_fen": 0,
                    "value_fen": int(row.get("value_fen", 0) or 0),
                    "discount_bp": 0,
                    "cap_fen": 0,
                    "valid_from": row.get("valid_from", ""),
                    "valid_until": row.get("valid_until", ""),
                    "status": "active",
                }
            if not is_coupon_available(template, total_fen, now):
                continue
            discount_fen = calc_discount(template, total_fen)
            if discount_fen <= 0:
                continue
            if discount_fen > total_fen - balance_fen - points_fen:
                continue
            available.append(
                {
                    "couponId": row["coupon_id"],
                    "title": row.get("title", ""),
                    "discountFen": discount_fen,
                    "validUntil": row.get("valid_until", ""),
                }
            )
        return {
            "orderId": order.id,
            "totalFen": total_fen,
            "balanceFen": balance_fen,
            "pointsFen": points_fen,
            "available": available,
            "remainFen": compute_remain_fen(total_fen, 0, balance_fen, points_fen),
        }

    async def apply_coupon(
        self, order_id: str, *, user_id: str, coupon_id: str
    ) -> dict:
        """应用券：校验并合并写快照（支付成功才核销）。"""
        from app.service.coupon.payment import CouponPaymentService

        payment_service = CouponPaymentService(
            inventory_service=self._inventory,
            template_repo=self._template_repo,
            order_repo=self._order_repo,
        )
        order = await self._owned_order(order_id, user_id)
        mobile = await self.resolve_mobile(user_id)
        return await payment_service.apply_coupon_snapshot(
            order, user_id=user_id, coupon_id=coupon_id, mobile=mobile
        )

    async def consume_on_payment(self, order: Order) -> None:
        """支付成功后核销券（幂等）。"""
        from app.service.coupon.payment import CouponPaymentService

        payment_service = CouponPaymentService(
            inventory_service=self._inventory,
            template_repo=self._template_repo,
            order_repo=self._order_repo,
        )
        await payment_service.consume_on_payment(order)

    async def refund_coupon(self, order: Order) -> None:
        """已支付全单退款退回券（幂等）。"""
        from app.service.coupon.payment import CouponPaymentService

        payment_service = CouponPaymentService(
            inventory_service=self._inventory,
            template_repo=self._template_repo,
            order_repo=self._order_repo,
        )
        await payment_service.refund_coupon(order)

    async def clear_applied(self, order: Order) -> None:
        """未支付取消/超时：只清券快照。"""
        from app.service.coupon.payment import CouponPaymentService

        payment_service = CouponPaymentService(
            inventory_service=self._inventory,
            template_repo=self._template_repo,
            order_repo=self._order_repo,
        )
        await payment_service.clear_coupon_snapshot(order)

    async def _owned_order(self, order_id: str, user_id: str) -> Order:
        order = await self._order_repo.get_order(order_id)
        if order is None or order.user_id != user_id:
            raise ValueError("订单不存在")
        return order

    @staticmethod
    def _total_fen(order: Order) -> int:
        from app.utils import yuan_to_fen

        return yuan_to_fen(order.total_amount)

    @staticmethod
    def _now_text() -> str:
        from app.service.order.payment_state import now_text

        return now_text()
