"""优惠券管理后台服务：模板维护、记录查询、local 发券。"""

import uuid

from app.config import settings
from app.logger import setup_logger
from app.models.coupon import (
    CouponGrant,
    CouponGrantStatus,
    CouponTemplate,
    CouponTemplateStatus,
    CouponType,
)
from app.models.member import CouponInventoryEntry, CouponStatus, LedgerSource
from app.repository.base import DatabaseHandle
from app.repository.coupon_grant_repo import CouponGrantRepo
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.utils import now_str

logger = setup_logger()


class AdminCouponService:
    """券模板 CRUD、记录查询与 local 发券。"""

    def __init__(self, db=None) -> None:
        """测试注入裸 aiosqlite 连接时统一包装为 DatabaseHandle。"""
        if db is not None and not isinstance(db, DatabaseHandle):
            db = DatabaseHandle(db)
        self._template_repo = CouponTemplateRepo(db)
        self._grant_repo = CouponGrantRepo(db)
        self._inventory_repo = CouponInventoryRepo(db)

    async def list_templates(self, *, status: str = "") -> dict:
        """模板列表。"""
        return {"templates": await self._template_repo.list(status=status)}

    async def create_template(self, payload: dict) -> dict:
        """创建券模板（local）。"""
        template_id = str(uuid.uuid4().hex[:16])
        template = self._template_from_payload(template_id, payload, source="local")
        await self._template_repo.save(template)
        row = await self._template_repo.get(template_id)
        return row or {}

    async def update_template(self, template_id: str, payload: dict) -> dict:
        """更新券模板。"""
        existing = await self._template_repo.get(template_id)
        if existing is None:
            raise ValueError("券模板不存在")
        template = self._template_from_payload(
            template_id, payload, source=str(existing.get("source", "local"))
        )
        await self._template_repo.save(template)
        row = await self._template_repo.get(template_id)
        return row or {}

    async def set_template_status(self, template_id: str, status: str) -> dict:
        """启停券模板。"""
        if status not in (CouponTemplateStatus.ACTIVE, CouponTemplateStatus.DISABLED):
            raise ValueError("模板状态不支持")
        await self._template_repo.set_status(template_id, status)
        row = await self._template_repo.get(template_id)
        return row or {}

    async def list_records(
        self, *, mobile: str = "", status: str = "", template_id: str = ""
    ) -> dict:
        """核销/退回记录与库存明细。"""
        records = await self._inventory_repo.list_all(
            mobile=mobile, status=status, template_id=template_id
        )
        grants = await self._grant_repo.list(mobile=mobile, template_id=template_id)
        return {"records": records, "grants": grants}

    async def grant_coupon(
        self, *, template_id: str, mobile: str, granted_by: str = "admin"
    ) -> dict:
        """local 模式按手机号发券（写 grants + 落 TAKE 行）。"""
        if settings.COUPON_AUTHORITY != "local":
            raise ValueError("当前为 youzan 权威模式，发券请走有赞后台")
        template = await self._template_repo.get(template_id)
        if template is None or template["status"] != CouponTemplateStatus.ACTIVE:
            raise ValueError("券模板不存在或已停用")
        coupon_id = str(uuid.uuid4().hex[:16])
        coupon_code = f"CP{now_str()[:10].replace('-', '')}{coupon_id[:8].upper()}"
        grant = CouponGrant(
            id=str(uuid.uuid4().hex[:16]),
            template_id=template_id,
            mobile=mobile,
            coupon_code=coupon_code,
            granted_by=granted_by,
            channel="admin",
        )
        async with self._inventory_repo.transaction():
            await self._grant_repo.insert(grant)
            await self._inventory_repo.insert(
                CouponInventoryEntry(
                    coupon_id=coupon_id,
                    coupon_group_id=template_id,
                    customer_id="",
                    mobile=mobile,
                    status=CouponStatus.TAKE,
                    title=str(template.get("name", "")),
                    value_fen=int(template.get("value_fen", 0) or 0),
                    detail_json="{}",
                    source=LedgerSource.LOCAL,
                    occurred_at=now_str(),
                    template_id=template_id,
                    valid_from=str(template.get("valid_from", "")),
                    valid_until=str(template.get("valid_until", "")),
                )
            )
        return {
            "couponId": coupon_id,
            "couponCode": coupon_code,
            "mobile": mobile,
            "templateId": template_id,
            "status": CouponGrantStatus.GRANTED,
        }

    def _template_from_payload(
        self, template_id: str, payload: dict, *, source: str
    ) -> CouponTemplate:
        coupon_type = str(payload.get("couponType", "")).upper()
        if coupon_type not in (
            CouponType.FULL_REDUCTION,
            CouponType.NO_THRESHOLD,
            CouponType.DISCOUNT,
        ):
            raise ValueError("券类型不支持")
        valid_from = str(payload.get("validFrom", "") or "")[:10]
        valid_until = str(payload.get("validUntil", "") or "")[:10]
        if valid_from and valid_until and valid_from > valid_until:
            raise ValueError("有效期起止不合法")
        return CouponTemplate(
            id=template_id,
            name=str(payload.get("name", "")),
            coupon_type=coupon_type,
            threshold_fen=int(payload.get("thresholdFen", 0) or 0),
            value_fen=int(payload.get("valueFen", 0) or 0),
            discount_bp=int(payload.get("discountBp", 0) or 0),
            cap_fen=int(payload.get("capFen", 0) or 0),
            valid_from=valid_from,
            valid_until=valid_until,
            scope_json="{}",
            status=str(payload.get("status", CouponTemplateStatus.ACTIVE)),
            source=source,
        )
