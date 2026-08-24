"""券模板数据访问层。"""

from app.models.coupon import CouponTemplate
from app.repository.base import BaseRepository
from app.utils import now_str


class CouponTemplateRepo(BaseRepository):
    """券模板仓储（youzan 同步 upsert / local 后台维护）。"""

    _COLS = (
        "id, name, coupon_type, threshold_fen, value_fen, discount_bp, cap_fen, "
        "valid_from, valid_until, scope_json, status, source, created_at, updated_at"
    )

    async def get(self, template_id: str) -> dict | None:
        """按模板 ID 读取。"""
        rows = await self._db.execute_fetchall(
            "SELECT " + self._COLS + " FROM coupon_templates WHERE id = ? LIMIT 1",
            (template_id,),
        )
        return rows[0] if rows else None

    async def list_active(self) -> list[dict]:
        """读取启用中的模板。"""
        return await self._db.execute_fetchall(
            "SELECT "
            + self._COLS
            + " FROM coupon_templates WHERE status = 'active' ORDER BY created_at DESC"
        )

    async def list_by_ids(self, ids: list[str]) -> list[dict]:
        """按模板 ID 批量读取（避免逐张查询 N+1）。"""
        if not ids:
            return []
        placeholders = ", ".join("?" for _ in ids)
        return await self._db.execute_fetchall(
            "SELECT "
            + self._COLS
            + " FROM coupon_templates WHERE id IN ("
            + placeholders
            + ")",
            tuple(ids),
        )

    async def list(self, *, status: str = "") -> list[dict]:
        """模板列表，可按状态筛选。"""
        if status:
            return await self._db.execute_fetchall(
                "SELECT "
                + self._COLS
                + " FROM coupon_templates WHERE status = ? ORDER BY created_at DESC",
                (status,),
            )
        return await self._db.execute_fetchall(
            "SELECT " + self._COLS + " FROM coupon_templates ORDER BY created_at DESC"
        )

    async def upsert_from_youzan(self, template: CouponTemplate) -> None:
        """有赞券模板幂等 upsert（按模板 ID）。"""
        now = now_str()
        await self._db.execute(
            "INSERT INTO coupon_templates (id, name, coupon_type, threshold_fen, value_fen, "
            "discount_bp, cap_fen, valid_from, valid_until, scope_json, status, source, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, coupon_type=excluded.coupon_type, "
            "threshold_fen=excluded.threshold_fen, value_fen=excluded.value_fen, "
            "discount_bp=excluded.discount_bp, cap_fen=excluded.cap_fen, "
            "valid_from=excluded.valid_from, valid_until=excluded.valid_until, "
            "scope_json=excluded.scope_json, source=excluded.source, updated_at=excluded.updated_at",
            (
                template.id,
                template.name,
                template.coupon_type,
                template.threshold_fen,
                template.value_fen,
                template.discount_bp,
                template.cap_fen,
                template.valid_from,
                template.valid_until,
                template.scope_json,
                template.status,
                template.source,
                now,
                now,
            ),
        )
        await self._db.commit()

    async def save(self, template: CouponTemplate) -> None:
        """local 后台创建/编辑模板（全量覆盖）。"""
        now = now_str()
        await self._db.execute(
            "INSERT INTO coupon_templates (id, name, coupon_type, threshold_fen, value_fen, "
            "discount_bp, cap_fen, valid_from, valid_until, scope_json, status, source, "
            "created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(id) DO UPDATE SET name=excluded.name, coupon_type=excluded.coupon_type, "
            "threshold_fen=excluded.threshold_fen, value_fen=excluded.value_fen, "
            "discount_bp=excluded.discount_bp, cap_fen=excluded.cap_fen, "
            "valid_from=excluded.valid_from, valid_until=excluded.valid_until, "
            "scope_json=excluded.scope_json, status=excluded.status, source=excluded.source, "
            "updated_at=excluded.updated_at",
            (
                template.id,
                template.name,
                template.coupon_type,
                template.threshold_fen,
                template.value_fen,
                template.discount_bp,
                template.cap_fen,
                template.valid_from,
                template.valid_until,
                template.scope_json,
                template.status,
                template.source,
                now,
                now,
            ),
        )
        await self._db.commit()

    async def set_status(self, template_id: str, status: str) -> None:
        """启停模板。"""
        await self._db.execute(
            "UPDATE coupon_templates SET status = ?, updated_at = ? WHERE id = ?",
            (status, now_str(), template_id),
        )
        await self._db.commit()
