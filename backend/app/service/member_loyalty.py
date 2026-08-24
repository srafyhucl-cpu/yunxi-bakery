"""会员积分/优惠券/会员卡全量导入服务。

按客户主档手机号拉取有赞积分余额、会员卡与优惠券，幂等写入
member_balance / coupon_inventory；points_ledger 由 Webhook 增量维护。
"""

import json

from app.logger import setup_logger
from app.models.member import (
    CouponInventoryEntry,
    LedgerSource,
)
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.service.coupon.template_sync import (
    extract_template_fields,
    parse_youzan_template,
    upsert_template_from_youzan,
)
from app.service.youzan.member_api import YouzanMemberApi
from app.service.youzan.member_helpers import to_fen, to_int

logger = setup_logger()


class MemberLoyaltyImportService:
    """全量导入服务：单客户三类账务数据幂等落库。"""

    def __init__(self, db, youzan_client, tenant_id: str = "yunxi") -> None:
        self._db = db
        self._tenant_id = tenant_id
        self._member_api = YouzanMemberApi(youzan_client)
        self._balance_repo = MemberBalanceRepo(db)
        self._coupon_repo = CouponInventoryRepo(db)
        self._template_repo = CouponTemplateRepo(db)
        self._coupon_detail_cache: dict[str, dict] = {}

    async def import_one(
        self, mobile: str, customer_id: str = "", *, should_apply: bool
    ) -> dict:
        """导入单个客户账务数据并返回统计；should_apply=False 时只查询不落库。"""
        self._coupon_detail_cache.clear()
        stats: dict = {
            "points_total": 0,
            "cards": 0,
            "coupons": 0,
            "errors": [],
        }
        try:
            points_total = _extract_points_total(
                await self._member_api.query_points(mobile)
            )
            stats["points_total"] = points_total
            if should_apply:
                async with self._balance_repo.transaction():
                    await self._balance_repo.upsert_identity(
                        mobile=mobile,
                        customer_id=customer_id,
                        points=points_total,
                    )

            cards = await self._member_api.list_customer_cards(mobile)
            stats["cards"] = len(cards)
            if should_apply and cards:
                async with self._balance_repo.transaction():
                    await self._balance_repo.upsert_identity(
                        mobile=mobile,
                        customer_id=customer_id,
                        card_alias=str(
                            cards[0].get("card_alias") or cards[0].get("alias") or ""
                        ),
                        card_no=str(cards[0].get("card_no") or ""),
                        card_status=str(cards[0].get("status") or ""),
                        is_member=1,
                    )

            coupons = await self._member_api.list_customer_coupons(mobile)
            stats["coupons"] = len(coupons)
            if should_apply:
                for coupon in coupons:
                    # B3.5（评审问题 1）：单张券写入口独占事务，失败整张回滚不污染他券
                    async with self._coupon_repo.transaction():
                        await self._upsert_coupon(coupon, mobile, customer_id)
        except Exception as exc:
            stats["errors"].append(f"{type(exc).__name__}: {exc}")
            logger.error("会员账务导入失败 mobile=%s err=%s", mobile, exc)
        return stats

    async def _upsert_coupon(self, coupon: dict, mobile: str, customer_id: str) -> None:
        """幂等写入一条优惠券库存记录。"""
        coupon_id = str(coupon.get("coupon_id") or coupon.get("id") or "")
        status = str(coupon.get("status") or "").upper()
        if not coupon_id or not status:
            return
        if await self._coupon_repo.get_by_dedup_key(coupon_id, status, mobile):
            return
        # 全量导入按 coupon_group_id 去重缓存详情，避免 N+1 反查
        group_id = str(coupon.get("coupon_group_id") or "")
        if group_id and group_id not in self._coupon_detail_cache:
            self._coupon_detail_cache[
                group_id
            ] = await self._member_api.get_coupon_group_detail(group_id)
        detail = self._coupon_detail_cache.get(group_id, {})
        tpl = parse_youzan_template(detail)
        await upsert_template_from_youzan(self._db, tpl, self._template_repo)
        fields = extract_template_fields(coupon, detail)
        await self._coupon_repo.insert(
            CouponInventoryEntry(
                coupon_id=coupon_id,
                coupon_group_id=str(coupon.get("coupon_group_id") or ""),
                customer_id=customer_id,
                mobile=mobile,
                status=status,
                order_no=str(coupon.get("order_no") or ""),
                title=str(coupon.get("title") or coupon.get("coupon_name") or ""),
                value_fen=to_fen(
                    coupon.get("value")
                    or coupon.get("amount")
                    or coupon.get("coupon_value")
                ),
                detail_json=json.dumps(coupon, ensure_ascii=False),
                source=LedgerSource.IMPORT,
                occurred_at="",
                template_id=fields["template_id"],
                valid_from=fields["valid_from"],
                valid_until=fields["valid_until"],
            )
        )


def _extract_points_total(payload: dict) -> int:
    """从积分查询响应中提取积分余额，兼容常见字段名。"""
    for key in ("points", "total", "balance", "current_points"):
        raw = payload.get(key)
        if raw is not None:
            return to_int(raw)
    return 0
