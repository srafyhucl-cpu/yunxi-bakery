"""储值余额会员解析与账务原子记账。"""

from app.models.customer_master import CustomerIdentityType
from app.models.stored_value import BalanceLedgerEntry
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.service.idempotency import (
    build_request_fingerprint,
    check_biz_binding,
    check_fingerprint_match,
    check_idempotency_contract,
)
from app.service.order.payment_state import extract_openid
from app.utils import now_str

DEFAULT_TENANT_ID = "yunxi"


class MemberBalanceService:
    """负责会员余额账户解析、加款/扣款与流水记账。"""

    def __init__(
        self,
        balance_repo: MemberBalanceRepo | None = None,
        ledger_repo: BalanceLedgerRepo | None = None,
        customer_repo: CustomerMasterRepo | None = None,
    ) -> None:
        self._balance_repo = balance_repo or MemberBalanceRepo(None)
        self._ledger_repo = ledger_repo or BalanceLedgerRepo(None)
        self._customer_repo = customer_repo or CustomerMasterRepo(None)

    @property
    def db_handle(self):
        """当前事务连接句柄，供调用方校验同连接复用。

        组合支付等跨服务事务要求余额变更与订单写入共享同一连接；
        不一致时调用方必须拒绝扣款。
        """
        return self._balance_repo._db

    async def resolve_mobile(self, user_id: str) -> str:
        """把小程序用户标识解析为会员手机号。"""
        openid = extract_openid(user_id)
        if not openid:
            raise ValueError("当前用户未绑定微信 openid")
        link = await self._customer_repo.get_identity_by_value(
            DEFAULT_TENANT_ID,
            CustomerIdentityType.MINIAPP_OPENID.value,
            openid,
        )
        if link is None:
            raise ValueError("当前用户未识别为会员")
        customer = await self._customer_repo.get_master(link.customer_id)
        if customer is None or not customer.primary_phone:
            raise ValueError("当前会员未登记手机号")
        return customer.primary_phone

    async def get_balance(self, user_id: str) -> dict:
        """读取会员储值余额与最近流水。"""
        mobile = await self.resolve_mobile(user_id)
        balance_fen = await self._balance_repo.get_stored_value_fen(mobile)
        ledger = await self._ledger_repo.list_by_mobile(mobile)
        return {"balanceFen": balance_fen, "mobile": mobile, "ledger": ledger}

    async def credit(
        self,
        *,
        user_id: str,
        mobile: str,
        amount_fen: int,
        biz_type: str,
        biz_id: str,
        unique_id: str,
        source: str,
    ) -> int:
        """加款并记账（幂等），返回加款后余额。

        占位、余额变更、流水补写在同一事务提交；幂等合同绑定账户主体、
        业务归属与金额，同键异主/异业/异额直接抛幂等冲突；重放返回原
        流水的余额快照，不读取当前余额冒充。
        """
        existing = await self._ledger_repo.get_by_unique_id(unique_id)
        if existing is not None:
            fingerprint = build_request_fingerprint(
                account=mobile,
                biz_type=biz_type,
                biz_id=biz_id,
                signed_amount=amount_fen,
            )
            check_idempotency_contract(
                existing=existing,
                account=mobile,
                amount_field="amount_fen",
                signed_amount=amount_fen,
                unique_id=unique_id,
            )
            check_biz_binding(
                existing=existing,
                biz_type=biz_type,
                biz_id=biz_id,
                unique_id=unique_id,
            )
            check_fingerprint_match(
                existing=existing,
                expected_fingerprint=fingerprint,
                unique_id=unique_id,
            )
            return int(existing["balance_after_fen"])
        async with self._balance_repo.transaction():
            fingerprint = build_request_fingerprint(
                account=mobile,
                biz_type=biz_type,
                biz_id=biz_id,
                signed_amount=amount_fen,
            )
            entry = BalanceLedgerEntry(
                unique_id=unique_id,
                user_id=user_id,
                mobile=mobile,
                amount_fen=amount_fen,
                balance_after_fen=0,
                biz_type=biz_type,
                biz_id=biz_id,
                source=source,
                occurred_at=now_str(),
                request_fingerprint=fingerprint,
            )
            if not await self._ledger_repo.insert_placeholder(entry):
                return await self._replay_existing(
                    unique_id, amount_fen, mobile, biz_type, biz_id
                )
            balance_after_fen = await self._balance_repo.credit_stored_value(
                mobile, amount_fen
            )
            await self._ledger_repo.complete_placeholder(unique_id, balance_after_fen)
            return balance_after_fen

    async def deduct(
        self,
        *,
        user_id: str,
        mobile: str,
        amount_fen: int,
        biz_type: str,
        biz_id: str,
        unique_id: str,
        source: str,
    ) -> int | None:
        """原子扣款并记账；余额不足返回 None，不扣款不记账。

        占位、余额变更、流水补写在同一事务提交；幂等合同绑定账户主体、
        业务归属与金额，同键异主/异业/异额直接抛幂等冲突；重放返回原
        流水的余额快照，不读取当前余额冒充。
        """
        existing = await self._ledger_repo.get_by_unique_id(unique_id)
        if existing is not None:
            fingerprint = build_request_fingerprint(
                account=mobile,
                biz_type=biz_type,
                biz_id=biz_id,
                signed_amount=-amount_fen,
            )
            check_idempotency_contract(
                existing=existing,
                account=mobile,
                amount_field="amount_fen",
                signed_amount=-amount_fen,
                unique_id=unique_id,
            )
            check_biz_binding(
                existing=existing,
                biz_type=biz_type,
                biz_id=biz_id,
                unique_id=unique_id,
            )
            check_fingerprint_match(
                existing=existing,
                expected_fingerprint=fingerprint,
                unique_id=unique_id,
            )
            return int(existing["balance_after_fen"])
        async with self._balance_repo.transaction():
            fingerprint = build_request_fingerprint(
                account=mobile,
                biz_type=biz_type,
                biz_id=biz_id,
                signed_amount=-amount_fen,
            )
            entry = BalanceLedgerEntry(
                unique_id=unique_id,
                user_id=user_id,
                mobile=mobile,
                amount_fen=-amount_fen,
                balance_after_fen=0,
                biz_type=biz_type,
                biz_id=biz_id,
                source=source,
                occurred_at=now_str(),
                request_fingerprint=fingerprint,
            )
            if not await self._ledger_repo.insert_placeholder(entry):
                return await self._replay_existing(
                    unique_id, -amount_fen, mobile, biz_type, biz_id
                )
            if not await self._balance_repo.deduct_stored_value_if_sufficient(
                mobile, amount_fen
            ):
                await self._ledger_repo.delete_placeholder(unique_id)
                return None
            balance_after_fen = await self._balance_repo.get_stored_value_fen(mobile)
            await self._ledger_repo.complete_placeholder(unique_id, balance_after_fen)
            return balance_after_fen

    async def _replay_existing(
        self, unique_id: str, amount_fen: int, mobile: str, biz_type: str, biz_id: str
    ) -> int:
        """占位竞争失败后按已存在流水重放，合同不一致直接拒绝。"""
        existing = await self._ledger_repo.get_by_unique_id(unique_id)
        if existing is None:
            raise RuntimeError(f"幂等占位冲突且无可见流水 unique_id={unique_id}")
        check_idempotency_contract(
            existing=existing,
            account=mobile,
            amount_field="amount_fen",
            signed_amount=amount_fen,
            unique_id=unique_id,
        )
        check_biz_binding(
            existing=existing, biz_type=biz_type, biz_id=biz_id, unique_id=unique_id
        )
        check_fingerprint_match(
            existing=existing,
            expected_fingerprint=build_request_fingerprint(
                account=mobile,
                biz_type=biz_type,
                biz_id=biz_id,
                signed_amount=amount_fen,
            ),
            unique_id=unique_id,
        )
        return int(existing["balance_after_fen"])
