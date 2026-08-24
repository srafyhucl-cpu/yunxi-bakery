"""客户群运营数据访问层。"""

from app.models.customer_group import CustomerGroup
from app.models.customer_group import GroupCampaign
from app.models.customer_group import GroupRegistration
from app.repository.base import BaseRepository


class CustomerGroupRepo(BaseRepository):
    """封装客户群、批次和登记数据读写。"""

    async def upsert_group(self, group: CustomerGroup) -> None:
        await self._db.execute(
            "INSERT INTO customer_groups ("
            "id, chat_id, opengid, name, owner_userid, source, status, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET "
            "opengid = excluded.opengid, "
            "name = excluded.name, "
            "owner_userid = excluded.owner_userid, "
            "source = excluded.source, "
            "status = excluded.status, "
            "updated_at = excluded.updated_at",
            (
                group.id,
                group.chat_id,
                group.opengid,
                group.name,
                group.owner_userid,
                group.source,
                group.status,
                group.created_at,
                group.updated_at,
            ),
        )
        await self._db.commit()

    async def get_group(self, group_id: str) -> CustomerGroup | None:
        rows = await self._db.execute_fetchall(
            "SELECT id, chat_id, opengid, name, owner_userid, source, status, "
            "created_at, updated_at FROM customer_groups WHERE id = ? LIMIT 1",
            (group_id,),
        )
        return CustomerGroup(**dict(rows[0])) if rows else None

    async def get_group_by_chat_id(self, chat_id: str) -> CustomerGroup | None:
        rows = await self._db.execute_fetchall(
            "SELECT id, chat_id, opengid, name, owner_userid, source, status, "
            "created_at, updated_at FROM customer_groups WHERE chat_id = ? LIMIT 1",
            (chat_id,),
        )
        return CustomerGroup(**dict(rows[0])) if rows else None

    async def list_groups(self, *, keyword: str = "") -> list[CustomerGroup]:
        clauses = ["status = 'active'"]
        params: list[object] = []
        if keyword:
            like = f"%{keyword}%"
            clauses.append("(name LIKE ? OR chat_id LIKE ? OR owner_userid LIKE ?)")
            params.extend([like, like, like])
        rows = await self._db.execute_fetchall(
            "SELECT id, chat_id, opengid, name, owner_userid, source, status, "
            "created_at, updated_at FROM customer_groups WHERE "
            + " AND ".join(clauses)
            + " ORDER BY updated_at DESC",
            tuple(params),
        )
        return [CustomerGroup(**dict(row)) for row in rows]

    async def insert_campaign(self, campaign: GroupCampaign) -> None:
        await self._db.execute(
            "INSERT INTO group_campaigns ("
            "id, group_id, title, status, starts_at, ends_at, summary_note, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                campaign.id,
                campaign.group_id,
                campaign.title,
                campaign.status,
                campaign.starts_at,
                campaign.ends_at,
                campaign.summary_note,
                campaign.created_at,
                campaign.updated_at,
            ),
        )
        await self._db.commit()

    async def get_campaign(self, campaign_id: str) -> GroupCampaign | None:
        rows = await self._db.execute_fetchall(
            "SELECT id, group_id, title, status, starts_at, ends_at, summary_note, "
            "created_at, updated_at FROM group_campaigns WHERE id = ? LIMIT 1",
            (campaign_id,),
        )
        return GroupCampaign(**dict(rows[0])) if rows else None

    async def list_campaigns(
        self,
        *,
        group_id: str = "",
        status: str = "",
    ) -> list[GroupCampaign]:
        clauses = ["1 = 1"]
        params: list[object] = []
        if group_id:
            clauses.append("group_id = ?")
            params.append(group_id)
        if status:
            clauses.append("status = ?")
            params.append(status)
        rows = await self._db.execute_fetchall(
            "SELECT id, group_id, title, status, starts_at, ends_at, summary_note, "
            "created_at, updated_at FROM group_campaigns WHERE "
            + " AND ".join(clauses)
            + " ORDER BY updated_at DESC",
            tuple(params),
        )
        return [GroupCampaign(**dict(row)) for row in rows]

    async def insert_registration(self, registration: GroupRegistration) -> None:
        await self._db.execute(
            "INSERT INTO group_registrations ("
            "id, campaign_id, group_id, user_id, customer_name, customer_phone, "
            "product_name, quantity, fulfillment_method, desired_time, address, "
            "remark, status, created_at, updated_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                registration.id,
                registration.campaign_id,
                registration.group_id,
                registration.user_id,
                registration.customer_name,
                registration.customer_phone,
                registration.product_name,
                registration.quantity,
                registration.fulfillment_method,
                registration.desired_time,
                registration.address,
                registration.remark,
                registration.status,
                registration.created_at,
                registration.updated_at,
            ),
        )
        await self._db.commit()

    async def update_registration_status(
        self,
        registration_id: str,
        status: str,
        updated_at: str,
    ) -> GroupRegistration | None:
        await self._db.execute(
            "UPDATE group_registrations SET status = ?, updated_at = ? WHERE id = ?",
            (status, updated_at, registration_id),
        )
        await self._db.commit()
        return await self.get_registration(registration_id)

    async def get_registration(self, registration_id: str) -> GroupRegistration | None:
        rows = await self._db.execute_fetchall(
            "SELECT id, campaign_id, group_id, user_id, customer_name, customer_phone, "
            "product_name, quantity, fulfillment_method, desired_time, address, "
            "remark, status, created_at, updated_at "
            "FROM group_registrations WHERE id = ? LIMIT 1",
            (registration_id,),
        )
        return GroupRegistration(**dict(rows[0])) if rows else None

    async def list_registrations(
        self,
        *,
        campaign_id: str = "",
        group_id: str = "",
        user_id: str = "",
    ) -> list[GroupRegistration]:
        clauses = ["1 = 1"]
        params: list[object] = []
        if campaign_id:
            clauses.append("campaign_id = ?")
            params.append(campaign_id)
        if group_id:
            clauses.append("group_id = ?")
            params.append(group_id)
        if user_id:
            clauses.append("user_id = ?")
            params.append(user_id)
        rows = await self._db.execute_fetchall(
            "SELECT id, campaign_id, group_id, user_id, customer_name, customer_phone, "
            "product_name, quantity, fulfillment_method, desired_time, address, "
            "remark, status, created_at, updated_at "
            "FROM group_registrations WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC",
            tuple(params),
        )
        return [GroupRegistration(**dict(row)) for row in rows]


__all__ = ["CustomerGroupRepo"]
