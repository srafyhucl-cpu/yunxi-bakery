"""积分账本：加款/扣款与流水写入（幂等）。"""

from app.models.member import LedgerSource, PointsLedgerEntry
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.points_ledger_repo import PointsLedgerRepo
from app.service.idempotency import (
    build_request_fingerprint,
    check_biz_binding,
    check_fingerprint_match,
    check_idempotency_contract,
)
from app.utils import now_str


class PointsLedgerService:
    """负责积分余额变动与流水记账。"""

    def __init__(
        self,
        balance_repo: MemberBalanceRepo | None = None,
        ledger_repo: PointsLedgerRepo | None = None,
    ) -> None:
        self._balance_repo = balance_repo or MemberBalanceRepo(None)
        self._ledger_repo = ledger_repo or PointsLedgerRepo(None)

    @property
    def ledger_repo(self) -> PointsLedgerRepo:
        """积分流水仓储访问器（供退款对账判定流水存在性）。"""
        return self._ledger_repo

    async def credit(
        self,
        *,
        mobile: str,
        amount: int,
        biz_type: str,
        biz_id: str,
        unique_id: str,
        event_type: str,
    ) -> int:
        """加款并写流水（幂等），返回变动后余额。

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
                signed_amount=amount,
            )
            check_idempotency_contract(
                existing=existing,
                account=mobile,
                amount_field="amount",
                signed_amount=amount,
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
            return int(existing["total"])
        async with self._balance_repo.transaction():
            fingerprint = build_request_fingerprint(
                account=mobile,
                biz_type=biz_type,
                biz_id=biz_id,
                signed_amount=amount,
            )
            entry = PointsLedgerEntry(
                unique_id=unique_id,
                mobile=mobile,
                amount=amount,
                total=0,
                event_type=event_type,
                source=LedgerSource.ORDER,
                biz_type=biz_type,
                biz_id=biz_id,
                occurred_at=now_str(),
                request_fingerprint=fingerprint,
            )
            if not await self._ledger_repo.insert_placeholder(entry):
                return await self._replay_existing(
                    unique_id, amount, mobile, biz_type, biz_id
                )
            balance_after = await self._balance_repo.credit_points(mobile, amount)
            await self._ledger_repo.complete_placeholder(unique_id, balance_after)
            return balance_after

    async def deduct(
        self,
        *,
        mobile: str,
        amount: int,
        biz_type: str,
        biz_id: str,
        unique_id: str,
        event_type: str,
    ) -> int | None:
        """原子扣款并写流水；余额不足返回 None，不扣款不记账。

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
                signed_amount=-amount,
            )
            check_idempotency_contract(
                existing=existing,
                account=mobile,
                amount_field="amount",
                signed_amount=-amount,
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
            return int(existing["total"])
        async with self._balance_repo.transaction():
            fingerprint = build_request_fingerprint(
                account=mobile,
                biz_type=biz_type,
                biz_id=biz_id,
                signed_amount=-amount,
            )
            entry = PointsLedgerEntry(
                unique_id=unique_id,
                mobile=mobile,
                amount=-amount,
                total=0,
                event_type=event_type,
                source=LedgerSource.ORDER,
                biz_type=biz_type,
                biz_id=biz_id,
                occurred_at=now_str(),
                request_fingerprint=fingerprint,
            )
            if not await self._ledger_repo.insert_placeholder(entry):
                return await self._replay_existing(
                    unique_id, -amount, mobile, biz_type, biz_id
                )
            if not await self._balance_repo.deduct_points_if_sufficient(mobile, amount):
                await self._ledger_repo.delete_placeholder(unique_id)
                return None
            balance_after = await self._balance_repo.get_points(mobile)
            await self._ledger_repo.complete_placeholder(unique_id, balance_after)
            return balance_after

    async def _replay_existing(
        self, unique_id: str, amount: int, mobile: str, biz_type: str, biz_id: str
    ) -> int:
        """占位竞争失败后按已存在流水重放，合同不一致直接拒绝。"""
        existing = await self._ledger_repo.get_by_unique_id(unique_id)
        if existing is None:
            raise RuntimeError(f"幂等占位冲突且无可见流水 unique_id={unique_id}")
        check_idempotency_contract(
            existing=existing,
            account=mobile,
            amount_field="amount",
            signed_amount=amount,
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
                signed_amount=amount,
            ),
            unique_id=unique_id,
        )
        return int(existing["total"])

    async def list_by_mobile(self, mobile: str) -> list[dict]:
        """读取手机号积分流水。"""
        return await self._ledger_repo.list_by_mobile(mobile)
