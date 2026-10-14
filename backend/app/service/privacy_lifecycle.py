"""主体隐私权利和数据保留周期服务。"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.repository.privacy_repo import PrivacyRepo, PrivacyRetentionCutoffs

MESSAGE_RETENTION_DAYS = 90
PROFILE_RETENTION_DAYS = 365
RETRIEVAL_LOG_RETENTION_DAYS = 30
ADDRESS_AUDIT_RETENTION_DAYS = 365
ORDER_RETENTION_DAYS = 2555
BACKUP_RETENTION_DAYS = 30


@dataclass(frozen=True)
class PrivacyRetentionPolicy:
    messages_days: int = MESSAGE_RETENTION_DAYS
    profiles_days: int = PROFILE_RETENTION_DAYS
    retrieval_logs_days: int = RETRIEVAL_LOG_RETENTION_DAYS
    address_audit_days: int = ADDRESS_AUDIT_RETENTION_DAYS
    orders_days: int = ORDER_RETENTION_DAYS
    backups_days: int = BACKUP_RETENTION_DAYS


class PrivacyLifecycleService:
    """编排主体导出、删除和自动保留期清理。"""

    def __init__(self, privacy_repo: PrivacyRepo) -> None:
        self._privacy_repo = privacy_repo

    async def export_subject(self, user_id: str) -> dict[str, Any]:
        return {
            "subject": {"user_id": user_id},
            "records": await self._privacy_repo.export_subject(user_id),
        }

    async def delete_subject(self, user_id: str) -> None:
        async with self._privacy_repo.transaction():
            await self._reject_live_wechat_prepay(user_id)
            await self._settle_holding_stored_value(user_id)
            await self._privacy_repo.delete_subject(user_id)

    async def _reject_live_wechat_prepay(self, user_id: str) -> None:
        """主体删除前拒绝仍在途的微信尾款腿。

        储值腿可以在删除前结清，微信腿不行：预下单会话在微信侧已生效、我方无法
        撤销，用户在订单被删除后仍能完成付款。付款通知按 `out_trade_no` 回查
        订单，订单一旦消失，到账资金既无法落账也无法建对账案件，只能等通知重投
        至 `dead_letter`——钱确实收到了，本地却没有任何凭据。

        这条腿无法用本地写入补偿，因此只能拒绝删除：请用户先完成或等待支付超时
        （订单转为 `cancelled` 且快照不再持有在途预支付标记）后再行使删除权。
        """
        live_orders = await self._privacy_repo.list_orders_with_live_wechat_prepay(
            user_id
        )
        if not live_orders:
            return
        raise ValueError(
            "存在微信支付在途订单，无法删除主体数据："
            f"orderIds={[order.id for order in live_orders]}；"
            "请先完成支付或等待支付超时关闭后重试"
        )

    async def _settle_holding_stored_value(self, user_id: str) -> None:
        """主体删除前结清仍被订单占用的储值腿。

        储值扣减记在 `balance_ledger`，该账本对 `orders` 没有外键；主体删除
        会连带删除订单，被扣金额将失去唯一退款凭据，且没有任何对账案件，
        构成储值永久滞留。已支付订单的储值已换货、不属占用，不得退回；
        只处理 `unpaid`/`partial` 且储值腿大于 0 的订单。

        结清失败即抛出并回滚整个删除事务：宁可让主体删除显式失败待人工
        介入，也不能让储值在删除成功的同时失去退款路径。
        """
        from app.repository.balance_ledger_repo import BalanceLedgerRepo
        from app.repository.customer_master_repo import CustomerMasterRepo
        from app.repository.member_balance_repo import MemberBalanceRepo
        from app.repository.order_repo import OrderRepo
        from app.service.stored_value.member import MemberBalanceService
        from app.service.stored_value.payment import StoredValueOrderPaymentService

        holding_orders = await self._privacy_repo.list_orders_holding_stored_value(
            user_id
        )
        if not holding_orders:
            return
        # 同连接固化：结清与主体删除必须在同一事务内，删除失败时储值回滚。
        db = self._privacy_repo._db
        payment_service = StoredValueOrderPaymentService(
            order_repo=OrderRepo(db),
            member_service=MemberBalanceService(
                balance_repo=MemberBalanceRepo(db),
                ledger_repo=BalanceLedgerRepo(db),
                customer_repo=CustomerMasterRepo(db),
            ),
        )
        for order in holding_orders:
            await payment_service.refund_order_balance(order)

    async def purge_expired(
        self,
        *,
        now: datetime | None = None,
        policy: PrivacyRetentionPolicy | None = None,
    ) -> dict[str, int]:
        current = now or datetime.now(timezone.utc)
        selected_policy = policy or PrivacyRetentionPolicy()
        cutoffs = PrivacyRetentionCutoffs(
            messages=_cutoff(current, selected_policy.messages_days),
            profiles=_cutoff(current, selected_policy.profiles_days),
            retrieval_logs=_cutoff(current, selected_policy.retrieval_logs_days),
            address_audit=_cutoff(current, selected_policy.address_audit_days),
            orders=_cutoff(current, selected_policy.orders_days),
        )
        async with self._privacy_repo.transaction():
            return await self._privacy_repo.purge_expired(cutoffs)


def _cutoff(now: datetime, days: int) -> str:
    return (now - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
