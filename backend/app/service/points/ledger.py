"""积分账本：加款/扣款与流水写入（幂等）。"""

from app.models.member import LedgerSource, PointsLedgerEntry
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.points_ledger_repo import PointsLedgerRepo
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
        """加款并写流水（幂等），返回变动后余额。"""
        if await self._ledger_repo.get_by_unique_id(unique_id):
            return await self._balance_repo.get_points(mobile)
        balance_after = await self._balance_repo.credit_points(mobile, amount)
        await self._ledger_repo.insert(
            PointsLedgerEntry(
                unique_id=unique_id,
                mobile=mobile,
                amount=amount,
                total=balance_after,
                event_type=event_type,
                source=LedgerSource.ORDER,
                biz_type=biz_type,
                biz_id=biz_id,
                occurred_at=now_str(),
            )
        )
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
        """原子扣款并写流水；余额不足返回 None，不扣款不记账。"""
        if await self._ledger_repo.get_by_unique_id(unique_id):
            return await self._balance_repo.get_points(mobile)
        if not await self._balance_repo.deduct_points_if_sufficient(mobile, amount):
            return None
        balance_after = await self._balance_repo.get_points(mobile)
        await self._ledger_repo.insert(
            PointsLedgerEntry(
                unique_id=unique_id,
                mobile=mobile,
                amount=-amount,
                total=balance_after,
                event_type=event_type,
                source=LedgerSource.ORDER,
                biz_type=biz_type,
                biz_id=biz_id,
                occurred_at=now_str(),
            )
        )
        return balance_after

    async def list_by_mobile(self, mobile: str) -> list[dict]:
        """读取手机号积分流水。"""
        return await self._ledger_repo.list_by_mobile(mobile)
