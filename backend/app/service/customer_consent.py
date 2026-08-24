"""顾客长期记忆同意状态服务。"""

from app.models.customer_profile import MemoryConsentStatus
from app.repository.customer_profile_repo import CustomerProfileRepo


class CustomerConsentService:
    """管理 consent ledger，并在撤回时删除长期画像。"""

    def __init__(self, profile_repo: CustomerProfileRepo) -> None:
        self._profile_repo = profile_repo

    async def get_status(self, channel: str, user_id: str) -> str:
        return await self._profile_repo.get_consent_status(channel, user_id)

    async def grant(self, channel: str, user_id: str) -> str:
        await self._profile_repo.set_consent_status(
            channel, user_id, MemoryConsentStatus.GRANTED.value
        )
        return MemoryConsentStatus.GRANTED.value

    async def revoke(self, channel: str, user_id: str) -> str:
        revoke_and_delete = getattr(self._profile_repo, "revoke_and_delete", None)
        if revoke_and_delete is not None:
            await revoke_and_delete(channel, user_id)
        else:
            await self._profile_repo.set_consent_status(
                channel, user_id, MemoryConsentStatus.REVOKED.value
            )
            await self._profile_repo.delete(channel, user_id)
        return MemoryConsentStatus.REVOKED.value
