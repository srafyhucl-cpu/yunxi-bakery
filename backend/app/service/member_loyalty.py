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
from app.service.youzan.member_helpers import (
    is_usable_int,
    map_coupon_status,
    to_fen,
    to_int,
)
from app.utils import format_millis_datetime

logger = setup_logger()

# 有赞「查询客户当前积分」响应里的积分数值字段，按可信度排序。
# `point` 是官方响应形状（`data.point`，2026-10-20 生产实测），
# 其余为历史兼容字段名，顺序与生产实测脚本保持一致。
POINTS_FIELD_CANDIDATES = (
    "point",
    "points",
    "total_points",
    "total",
    "balance",
    "current_points",
    "points_total",
    "available_points",
)
# 有赞侧查不到积分数据时的稳定错误标记：调用方可据此区分「未知」与「0 分」。
POINTS_UNAVAILABLE_ERROR = (
    "youzan_points_unavailable: 有赞侧查不到积分数据，已跳过积分镜像"
)


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
        """导入单个客户账务数据并返回统计；should_apply=False 时只查询不落库。

        积分 / 会员卡 / 优惠券三类账务**互不连坐**：某一类采集失败只记错误，
        其余两类必须照常采集。否则有赞接口一次抖动就会让该会员的券与卡整段
        漏采（漏券/漏卡）。
        """
        self._coupon_detail_cache.clear()
        stats: dict = {
            "points_total": 0,
            "cards": 0,
            "coupons": 0,
            "errors": [],
        }
        try:
            await self._sync_points(
                mobile, customer_id, stats, should_apply=should_apply
            )
        except Exception as exc:
            _record_collect_error(stats, "积分", mobile, exc)
        try:
            await self._sync_cards(
                mobile, customer_id, stats, should_apply=should_apply
            )
        except Exception as exc:
            _record_collect_error(stats, "会员卡", mobile, exc)
        try:
            await self._sync_coupons(
                mobile, customer_id, stats, should_apply=should_apply
            )
        except Exception as exc:
            _record_collect_error(stats, "优惠券", mobile, exc)
        return stats

    async def _sync_cards(
        self,
        mobile: str,
        customer_id: str,
        stats: dict,
        *,
        should_apply: bool,
    ) -> None:
        """拉取有赞会员卡并写会员身份快照。"""
        cards = await self._member_api.list_customer_cards(mobile)
        stats["cards"] = len(cards)
        if not should_apply or not cards:
            return
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

    async def _sync_coupons(
        self,
        mobile: str,
        customer_id: str,
        stats: dict,
        *,
        should_apply: bool,
    ) -> None:
        """拉取有赞买家券并幂等写入券库存。"""
        coupons = await self._member_api.list_customer_coupons(mobile)
        stats["coupons"] = len(coupons)
        if not should_apply:
            return
        for coupon in coupons:
            # B3.5（评审问题 1）：单张券写入口独占事务，失败整张回滚不污染他券
            async with self._coupon_repo.transaction():
                await self._upsert_coupon(coupon, mobile, customer_id)

    async def _sync_points(
        self,
        mobile: str,
        customer_id: str,
        stats: dict,
        *,
        should_apply: bool,
    ) -> None:
        """拉取有赞积分并按锚点口径镜像到本地。

        有赞侧查不到积分数据时**不写库**：把「未知」当成 0 会把会员已有的
        积分锚点清零，属于凭空造数据；此时只在统计里留下稳定错误标记。
        """
        payload = await self._member_api.query_points(mobile)
        points_total = _extract_points_total(payload)
        if points_total is None:
            stats["errors"].append(POINTS_UNAVAILABLE_ERROR)
            logger.error("有赞侧查不到积分数据，跳过积分镜像 mobile=%s", mobile)
            return
        stats["points_total"] = points_total
        if not should_apply:
            return
        async with self._balance_repo.transaction():
            # r79（`M-20260926-030`）：导入同样只表达**外部权威总额**，
            # 改走锚点口径。此前用 `upsert_identity(points=...)` 绝对覆盖
            # 会抹掉小程序订单已发的本地积分净额。
            await self._balance_repo.mirror_youzan_points(
                mobile=mobile,
                customer_id=customer_id,
                youzan_total=points_total,
            )

    async def _upsert_coupon(self, coupon: dict, mobile: str, customer_id: str) -> None:
        """幂等写入一条优惠券库存记录。

        有赞买家券接口返回的是上游词表（VALID/USED），必须映射成本地
        `CouponStatus` 后才能落库：本地券账本只认 TAKE/CONSUME/BACK，
        上游词表原样落库会让券永远匹配不上本地引擎的 TAKE 判断（券可见
        但无法核销，等同漏券）。无法映射的状态（已失效/已过期）直接跳过，
        不能退化成某个默认状态。
        """
        coupon_id = str(coupon.get("coupon_id") or coupon.get("id") or "")
        status = map_coupon_status(
            coupon.get("youzan_coupon_status") or coupon.get("status")
        )
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
                coupon_group_id=group_id,
                customer_id=customer_id,
                mobile=mobile,
                status=status,
                order_no=str(
                    coupon.get("used_in_order_no") or coupon.get("order_no") or ""
                ),
                title=str(coupon.get("title") or coupon.get("coupon_name") or tpl.name),
                value_fen=tpl.value_fen
                or to_fen(
                    coupon.get("value")
                    or coupon.get("amount")
                    or coupon.get("coupon_value")
                ),
                detail_json=json.dumps(coupon, ensure_ascii=False),
                source=LedgerSource.IMPORT,
                occurred_at=format_millis_datetime(coupon.get("take_at")),
                template_id=fields["template_id"],
                valid_from=fields["valid_from"],
                valid_until=fields["valid_until"],
            )
        )


def _record_collect_error(stats: dict, label: str, mobile: str, exc: Exception) -> None:
    """记录单个账务采集环节的失败。

    三类账务互不连坐：某一类失败只在此留痕，其余两类照常采集。
    """
    stats["errors"].append(f"{label}采集失败: {type(exc).__name__}: {exc}")
    logger.error("有赞%s采集失败 mobile=%s err=%s", label, mobile, exc)


def _extract_points_total(payload: dict) -> int | None:
    """从积分查询响应中提取积分余额；查不到数据时返回 None。

    权威写入路径必须区分「确实是 0 分」与「查不到」：字段缺失、空串与
    非数值一律返回 None，由调用方跳过积分镜像。把「未知」折成 0 会把会员
    已有的积分锚点清零。
    """
    for key in POINTS_FIELD_CANDIDATES:
        if key not in payload:
            continue
        raw = payload.get(key)
        if not is_usable_int(raw):
            continue
        return to_int(raw)
    return None
