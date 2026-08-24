"""储值充值服务。"""

from datetime import datetime
from uuid import uuid4

from app.config import settings
from app.constants.stored_value import (
    MAX_RECHARGE_FEN,
    MIN_RECHARGE_FEN,
    RECHARGE_LIST_PAGE_SIZE,
)
from app.models.stored_value import (
    BalanceBizType,
    BalanceSource,
    RechargeOrder,
    RechargeStatus,
)
from app.repository.recharge_repo import RechargeRepo
from app.service.stored_value.member import MemberBalanceService

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
RECHARGE_ID_PREFIX = "r_"


class RechargeService:
    """负责充值单创建、支付确认、取消与查询。"""

    def __init__(
        self,
        recharge_repo: RechargeRepo | None = None,
        member_service: MemberBalanceService | None = None,
    ) -> None:
        self._recharge_repo = recharge_repo or RechargeRepo(None)
        self._member_service = member_service or MemberBalanceService()

    async def create_recharge(self, user_id: str, amount_fen: int) -> dict:
        """创建充值单。"""
        if amount_fen < MIN_RECHARGE_FEN:
            raise ValueError(f"充值金额不能低于 {MIN_RECHARGE_FEN} 分")
        if amount_fen > MAX_RECHARGE_FEN:
            raise ValueError(f"充值金额不能超过 {MAX_RECHARGE_FEN} 分")
        mobile = await self._member_service.resolve_mobile(user_id)
        now = datetime.now().strftime(TIME_FORMAT)
        recharge = RechargeOrder(
            id=self._build_recharge_id(),
            user_id=user_id,
            mobile=mobile,
            amount_fen=amount_fen,
            status=RechargeStatus.UNPAID,
            created_at=now,
            updated_at=now,
        )
        async with self._recharge_repo.transaction():
            await self._recharge_repo.create(recharge)
        return self._serialize(recharge)

    async def cancel_unpaid_recharge(
        self,
        recharge_id: str,
        *,
        user_id: str,
    ) -> dict:
        """取消未支付充值单。"""
        existing = await self._owned_recharge(recharge_id, user_id)
        if existing.status == RechargeStatus.CANCELLED:
            return self._serialize(existing)
        if existing.status != RechargeStatus.UNPAID:
            raise ValueError("当前充值单状态不允许取消")
        updated = await self._recharge_repo.cancel_if_unpaid(recharge_id)
        if updated is None:
            latest = await self._owned_recharge(recharge_id, user_id)
            if latest.status == RechargeStatus.CANCELLED:
                return self._serialize(latest)
            raise ValueError("充值单状态更新冲突")
        return self._serialize(updated)

    async def confirm_mock_recharge_payment(
        self,
        recharge_id: str,
        *,
        user_id: str,
    ) -> dict:
        """mock 支付确认充值，成功即入账余额（幂等防重复入账）。"""
        if not settings.ALLOW_MOCK_PAYMENT:
            raise ValueError("生产环境已禁用 mock 支付")
        async with self._recharge_repo.transaction():
            existing = await self._owned_recharge(recharge_id, user_id)
            if existing.status == RechargeStatus.PAID:
                return self._serialize(existing)
            if existing.status != RechargeStatus.UNPAID:
                raise ValueError("当前充值单状态不允许支付")
            now = datetime.now().strftime(TIME_FORMAT)
            updated = await self._recharge_repo.mark_paid_if_unpaid(
                recharge_id,
                payment_method="mock",
                paid_at=now,
            )
            if updated is None:
                raise ValueError("充值单支付状态更新冲突")
            await self._member_service.credit(
                user_id=user_id,
                mobile=existing.mobile,
                amount_fen=existing.amount_fen,
                biz_type=BalanceBizType.RECHARGE,
                biz_id=existing.id,
                unique_id=f"recharge:{existing.id}",
                source=BalanceSource.RECHARGE,
            )
        return self._serialize(updated)

    async def list_user_recharges(self, user_id: str) -> list[dict]:
        """读取当前用户充值单列表。"""
        recharges = await self._recharge_repo.list_by_user(
            user_id,
            limit=RECHARGE_LIST_PAGE_SIZE,
        )
        return [self._serialize(recharge) for recharge in recharges]

    async def _owned_recharge(
        self,
        recharge_id: str,
        user_id: str,
    ) -> RechargeOrder:
        recharge = await self._recharge_repo.get(recharge_id)
        if recharge is None or recharge.user_id != user_id:
            raise ValueError("充值单不存在")
        return recharge

    def _build_recharge_id(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        return f"{RECHARGE_ID_PREFIX}{timestamp}{uuid4().hex[:8]}"

    @staticmethod
    def _serialize(recharge: RechargeOrder) -> dict:
        return {
            "rechargeId": recharge.id,
            "amountFen": recharge.amount_fen,
            "status": recharge.status,
            "paymentMethod": recharge.payment_method,
            "paidAt": recharge.paid_at,
            "createdAt": recharge.created_at,
        }
