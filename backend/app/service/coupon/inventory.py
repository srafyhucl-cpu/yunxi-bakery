"""券库存账本：核销/退回的幂等与事务边界。"""

import sqlite3

from app.config import settings
from app.logger import setup_logger
from app.models.member import CouponStatus
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_reconcile_repo import CouponReconcileRepo

logger = setup_logger()

# 本地权威来源：只有这些来源的状态行才由本单账务裁决。webhook / import 是外部
# 观察（COUPON_AUTHORITY=youzan 时有赞为券权威方），平台无权否认其已核销事实。
_LOCAL_SOURCES = frozenset({"order", "local"})

# 外部核销冲突的对账案件原因（支付腿与退款腿共用，保证只开一条案件）。
REASON_EXTERNAL_CONSUME_CONFLICT = "external_consume_conflict"


def _is_local_state(state: dict | None) -> bool:
    """判断状态行是否来自本地账务来源。"""
    if state is None:
        return False
    return str(state.get("source", "") or "") in _LOCAL_SOURCES


def _consumed_by_this_order(state: dict | None, order_no: str) -> bool:
    """判断该 CONSUME 状态行是否由本单本地核销产生。"""
    if state is None or state.get("status") != CouponStatus.CONSUME:
        return False
    return _is_local_state(state) and str(state.get("order_no", "") or "") == order_no


class CouponInventoryService:
    """券生命周期账本（核销/退回，幂等）。"""

    def __init__(self, db) -> None:
        self._repo = CouponInventoryRepo(db)
        self._reconcile_repo = CouponReconcileRepo(db)

    async def _open_external_consume_case(
        self,
        coupon_id: str,
        mobile: str,
        *,
        order_no: str,
        deducted_fen: int,
        state: dict,
        leg: str,
    ) -> None:
        """外部权威侧已核销同一张券：追加对账案件，不核销也不回滚收款。

        平台不是该券的权威方，既不能否认外部已核销的事实，也不能再插一条本地
        CONSUME（那会让一张券抵扣两单）。此处只把被争议的抵扣金额如实留痕，
        由平台按案件吸收或向客户追偿——有界可对账的损失，优于让已到账收款永久
        失账。leg 仅用于日志区分支付腿 / 退款腿，case_key 相同故只留一条案件。
        """
        created = await self._reconcile_repo.append(
            case_key=(f"{REASON_EXTERNAL_CONSUME_CONFLICT}:{order_no}:{coupon_id}"),
            coupon_id=coupon_id,
            mobile=mobile,
            order_id=order_no,
            reason=REASON_EXTERNAL_CONSUME_CONFLICT,
            deducted_fen=deducted_fen,
            external_order_no=str(state.get("order_no", "") or ""),
            external_source=str(state.get("source", "") or ""),
            note=(
                f"券已被外部来源核销于订单 "
                f"{state.get('order_no', '')}，本单不核销，抵扣金额待对账（{leg}）"
            ),
        )
        logger.warning(
            "券被外部核销冲突：order=%s coupon=%s external_order=%s "
            "external_source=%s deducted_fen=%s 开案=%s（%s）",
            order_no,
            coupon_id,
            state.get("order_no", ""),
            state.get("source", ""),
            deducted_fen,
            created,
            leg,
        )

    async def consume_once(
        self,
        coupon_id: str,
        mobile: str,
        *,
        order_no: str,
        deducted_fen: int,
        occurred_at: str,
    ) -> dict | None:
        """核销一张券：事务内校验最新态=TAKE 并插入 CONSUME 行（幂等）。

        authority 取 settings.COUPON_AUTHORITY：youzan 模式下 import/webhook
        镜像行是有效来源；local 模式下只认 order/local 行。并发双核销由唯一索引
        (coupon_id, status, mobile) 兜底，IntegrityError 转幂等返回。

        同单重复核销幂等返回；**本地**跨订单核销抛 ValueError（防一张券抵扣两单，
        余额/组合/储值支付路径在事务内，抛错整体回滚，支付不落账）。

        **外部**跨订单核销（r77）：本单无权否认，也不本地核销，更不得回滚已
        到账的收款——改为不核销 + 开对账案件 + 放行支付（见
        `_open_external_consume_case`）。
        """
        authority = settings.COUPON_AUTHORITY
        async with self._repo.transaction():
            existing = await self._repo.get_latest_state(
                coupon_id, mobile, authority=authority
            )
            if existing is not None and existing["status"] == CouponStatus.CONSUME:
                if str(existing.get("order_no", "") or "") == order_no:
                    return existing
                if not _is_local_state(existing):
                    await self._open_external_consume_case(
                        coupon_id,
                        mobile,
                        order_no=order_no,
                        deducted_fen=deducted_fen,
                        state=existing,
                        leg="支付",
                    )
                    return existing
                raise ValueError("优惠券已被其他订单核销")
            try:
                consumed = await self._repo.consume(
                    coupon_id,
                    mobile,
                    order_no=order_no,
                    deducted_fen=deducted_fen,
                    consumed_at=occurred_at,
                    occurred_at=occurred_at,
                    authority=authority,
                )
                if consumed is not None:
                    return consumed
                # 核销未落行（券已被退回、已过期或状态缺失）必须按失败处理：
                # 静默返回 None 会让支付路径把「券未核销」当成「已核销」，
                # 使订单按券面抵扣完成支付，形成一张券抵扣两单的资产损失。
                latest = await self._repo.get_latest_state(
                    coupon_id, mobile, authority=authority
                )
                if (
                    latest is not None
                    and latest["status"] == CouponStatus.CONSUME
                    and str(latest.get("order_no", "") or "") == order_no
                ):
                    return latest
                raise ValueError("优惠券核销未落账，请对账处理")
            except sqlite3.IntegrityError:
                # 并发核销冲突：重读最新态，同单幂等返回、跨单拒绝
                latest = await self._repo.get_latest_state(
                    coupon_id, mobile, authority=authority
                )
                if latest is not None:
                    if str(latest.get("order_no", "") or "") == order_no:
                        return latest
                    if not _is_local_state(latest):
                        await self._open_external_consume_case(
                            coupon_id,
                            mobile,
                            order_no=order_no,
                            deducted_fen=deducted_fen,
                            state=latest,
                            leg="支付",
                        )
                        return latest
                    raise ValueError("优惠券已被其他订单核销")
                raise

    async def refund_once(
        self,
        coupon_id: str,
        mobile: str,
        *,
        order_no: str,
        occurred_at: str,
        deducted_fen: int = 0,
    ) -> dict | None:
        """退回已核销券：事务内校验最新态=CONSUME 并插入 BACK 行（幂等）。

        同单重复退回幂等返回；跨订单退回抛 ValueError（与核销同源防双花）。

        r77 归属守卫：只有**本单本地核销过**的 CONSUME 才允许写 BACK。外部
        权威侧（或另一订单）已核销时本单从未消费过该券，写 BACK 会把已消耗的
        券重新放回可用池形成二次使用；此时静默不写 BACK 并保留案件。
        """
        authority = settings.COUPON_AUTHORITY
        async with self._repo.transaction():
            existing = await self._repo.get_latest_state(
                coupon_id, mobile, authority=authority
            )
            if existing is not None and existing["status"] == CouponStatus.BACK:
                if str(existing.get("order_no", "") or "") == order_no:
                    return existing
                raise ValueError("优惠券已被其他订单退回")
            if (
                existing is not None
                and existing["status"] == CouponStatus.CONSUME
                and not _consumed_by_this_order(existing, order_no)
            ):
                if not _is_local_state(existing):
                    await self._open_external_consume_case(
                        coupon_id,
                        mobile,
                        order_no=order_no,
                        deducted_fen=deducted_fen,
                        state=existing,
                        leg="退款",
                    )
                else:
                    logger.error(
                        "券由其他本地订单核销，本单无权退回：order=%s coupon=%s "
                        "consumed_by=%s",
                        order_no,
                        coupon_id,
                        existing.get("order_no", ""),
                    )
                return None
            try:
                return await self._repo.refund(
                    coupon_id,
                    mobile,
                    order_no=order_no,
                    refunded_at=occurred_at,
                    occurred_at=occurred_at,
                    authority=authority,
                )
            except sqlite3.IntegrityError:
                # 并发退回冲突：重读最新态，同单幂等返回、跨单拒绝
                latest = await self._repo.get_latest_state(
                    coupon_id, mobile, authority=authority
                )
                if latest is not None:
                    if str(latest.get("order_no", "") or "") == order_no:
                        return latest
                    raise ValueError("优惠券已被其他订单退回")
                raise
