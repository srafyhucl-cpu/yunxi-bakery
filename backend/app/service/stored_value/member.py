"""储值余额会员解析与账务原子记账。"""

from app.models.customer_master import CustomerIdentityType
from app.models.stored_value import BalanceLedgerEntry
from app.repository.balance_ledger_repo import BalanceLedgerRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.service.idempotency import (
    IdempotencyConflict,
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
        bonus_fen: int = 0,
    ) -> int:
        """加款并记账（幂等），返回加款后余额。

        bonus_fen 为本次加款中的赠送金部分，必须满足 0 <= bonus_fen <= amount_fen，
        其余计入实充本金；流水按该拆分落库，使后续退款可按原结构还原。
        占位、余额变更、流水补写在同一事务提交；幂等合同绑定账户主体、
        业务归属与金额，同键异主/异业/异额直接抛幂等冲突；重放返回原
        流水的余额快照，不读取当前余额冒充。
        """
        if bonus_fen < 0 or bonus_fen > amount_fen:
            raise ValueError("赠送金额必须在 0 到加款金额之间")
        principal_delta_fen = amount_fen - bonus_fen
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
            self._check_split_replay(
                existing, principal_delta_fen, bonus_fen, unique_id
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
                principal_delta_fen=principal_delta_fen,
                bonus_delta_fen=bonus_fen,
            )
            if not await self._ledger_repo.insert_placeholder(entry):
                return await self._replay_existing(
                    unique_id,
                    amount_fen,
                    mobile,
                    biz_type,
                    biz_id,
                    principal_delta_fen=principal_delta_fen,
                    bonus_delta_fen=bonus_fen,
                )
            balance_after_fen = await self._balance_repo.credit_stored_value(
                mobile, amount_fen, bonus_fen
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

        扣款优先扣赠送金、不足部分再扣本金，实际拆分写入流水，
        使退款可精确还原结构。占位、余额变更、流水补写在同一事务提交；
        幂等合同绑定账户主体、业务归属与金额，同键异主/异业/异额直接抛
        幂等冲突；重放返回原流水的余额快照，不读取当前余额冒充。
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
            # 占位已持有写锁，此时读账户结构并与余额变更同事务，读到的
            # 赠送金/本金即本次扣减依据；原子扣款仍会二次校验结构，防扣穿。
            row = await self._balance_repo.get_by_mobile(mobile)
            current_bonus_fen = int(row.get("bonus_fen", 0) or 0) if row else 0
            deduct_bonus_fen = min(current_bonus_fen, amount_fen)
            deduct_principal_fen = amount_fen - deduct_bonus_fen
            if not await self._balance_repo.deduct_stored_value_with_split(
                mobile, amount_fen, deduct_principal_fen, deduct_bonus_fen
            ):
                await self._ledger_repo.delete_placeholder(unique_id)
                return None
            balance_after_fen = await self._balance_repo.get_stored_value_fen(mobile)
            await self._ledger_repo.complete_placeholder(
                unique_id,
                balance_after_fen,
                principal_delta_fen=-deduct_principal_fen,
                bonus_delta_fen=-deduct_bonus_fen,
            )
            return balance_after_fen

    async def get_ledger_entry(self, unique_id: str) -> dict | None:
        """按幂等键读取流水（退款按原拆分还原结构时使用）。"""
        return await self._ledger_repo.get_by_unique_id(unique_id)

    @staticmethod
    def _check_split_replay(
        existing: dict, principal_delta_fen: int, bonus_delta_fen: int, unique_id: str
    ) -> None:
        """同键重放时校验本金/赠送金拆分一致，结构不同直接拒绝。

        v040 迁移已把历史流水按本金回填，因此历史流水仍按本金语义比对。
        """
        stored_principal = int(existing.get("principal_delta_fen", 0) or 0)
        stored_bonus = int(existing.get("bonus_delta_fen", 0) or 0)
        if stored_principal == principal_delta_fen and stored_bonus == bonus_delta_fen:
            return
        raise IdempotencyConflict(
            f"幂等键金额冲突 unique_id={unique_id} "
            f"existing_principal={stored_principal} existing_bonus={stored_bonus} "
            f"expected_principal={principal_delta_fen} expected_bonus={bonus_delta_fen}"
        )

    async def _replay_existing(
        self,
        unique_id: str,
        amount_fen: int,
        mobile: str,
        biz_type: str,
        biz_id: str,
        principal_delta_fen: int | None = None,
        bonus_delta_fen: int | None = None,
    ) -> int:
        """占位竞争失败后按已存在流水重放，合同不一致直接拒绝。

        credit 等拆分可复算的调用方传入本次期望拆分：同键同额但本金/赠送金
        结构不同的请求必须冲突，不能静默复用先到的结构。deduct 的实际拆分
        取决于当时余额、不可复算，故不传，保持原有校验范围。
        """
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
        if principal_delta_fen is not None and bonus_delta_fen is not None:
            self._check_split_replay(
                existing, principal_delta_fen, bonus_delta_fen, unique_id
            )
        return int(existing["balance_after_fen"])
