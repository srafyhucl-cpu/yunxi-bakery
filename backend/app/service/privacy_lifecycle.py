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
            await self._privacy_repo.delete_subject(user_id)

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
