"""有赞会员域 Webhook 事件处理器。

处理四类会员账务事件并幂等写入账务域：
- SCRM_CUSTOMER_EVENT        → 客户身份/会员标记更新（member_balance）
- POINTS                     → points_ledger 流水 + member_balance 余额快照
- COUPON_CUSTOMER_PROMOTION  → coupon_inventory（反查券详情补全）
- SCRM_CUSTOMER_CARD         → 会员卡状态更新（member_balance）
"""

import json

from app.config import settings
from app.logger import setup_logger
from app.models.customer_master import CustomerIdentityType
from app.models.member import (
    CouponInventoryEntry,
    LedgerSource,
    MemberEventType,
    PointsLedgerEntry,
)
from app.models.youzan_webhook_event import (
    YouzanWebhookBusinessType,
    YouzanWebhookStatus,
)
from app.repository.coupon_inventory_repo import CouponInventoryRepo
from app.repository.customer_master_repo import CustomerMasterRepo
from app.repository.member_balance_repo import MemberBalanceRepo
from app.repository.points_ledger_repo import PointsLedgerRepo
from app.service.coupon.template_sync import (
    extract_template_fields,
    parse_youzan_template,
    upsert_template_from_youzan,
)
from app.service.youzan.audit_helper import mark_audit
from app.service.youzan.member_api import YouzanMemberApi
from app.service.youzan.member_helpers import to_bool, to_fen, to_int

logger = setup_logger()

DEFAULT_TENANT_ID = "yunxi"

MEMBER_EVENT_TYPES: frozenset[str] = frozenset(
    {
        MemberEventType.CUSTOMER,
        MemberEventType.POINTS,
        MemberEventType.COUPON,
        MemberEventType.CARD,
    }
)


def _as_handle(db):
    """裸 aiosqlite 连接包装为 DatabaseHandle（含 transaction()）。"""
    from app.repository.base import DatabaseHandle

    if hasattr(db, "transaction"):
        return db
    return DatabaseHandle(db)


async def handle_member_event(
    db,
    youzan_client,
    event_type: str,
    msg_obj: dict,
    updated_at_str: str,
    audit_repo=None,
    audit_id: int | None = None,
    msg_id: str = "",
) -> None:
    """按事件类型分发会员域 Webhook 写入。

    B3.5（评审问题 1）：账务写入口（积分 / 券 / 余额快照）由本分发器独占
    事务边界，仓储不自提交；审计标记（audit_repo 自提交）在事务外单独落库，
    账务写入失败整体回滚，不污染审计。
    """
    event_type_lower = event_type.lower()
    balance_repo = MemberBalanceRepo(db)
    customer_repo = CustomerMasterRepo(db)
    try:
        async with _as_handle(db).transaction():
            if event_type_lower == MemberEventType.POINTS:
                await _handle_points_event(
                    db, balance_repo, customer_repo, msg_obj, updated_at_str
                )
            elif event_type_lower == MemberEventType.COUPON:
                await _handle_coupon_event(
                    db,
                    balance_repo,
                    customer_repo,
                    youzan_client,
                    msg_obj,
                    updated_at_str,
                )
            elif event_type_lower == MemberEventType.CUSTOMER:
                await _handle_customer_event(balance_repo, msg_obj)
            elif event_type_lower == MemberEventType.CARD:
                await _handle_card_event(balance_repo, msg_obj)
            else:
                logger.warning(
                    "未知会员事件类型，跳过: type=%s msg_id=%s", event_type, msg_id
                )
                await mark_audit(
                    audit_repo,
                    audit_id,
                    YouzanWebhookStatus.SKIPPED,
                    "member_unknown_type",
                    business_type=YouzanWebhookBusinessType.MEMBER,
                    error_type="unknown_event_type",
                )
                return
        await mark_audit(
            audit_repo,
            audit_id,
            YouzanWebhookStatus.PROCESSED,
            "member_processed",
            business_type=YouzanWebhookBusinessType.MEMBER,
            business_key=_business_key(msg_obj),
        )
    except Exception as exc:
        logger.error("处理有赞会员事件失败: type=%s err=%s", event_type, exc)
        await mark_audit(
            audit_repo,
            audit_id,
            YouzanWebhookStatus.FAILED,
            "member_failed",
            business_type=YouzanWebhookBusinessType.MEMBER,
            error_type=type(exc).__name__,
            error_message=str(exc),
            business_key=_business_key(msg_obj),
        )
        raise


async def _handle_points_event(
    db, balance_repo, customer_repo, msg_obj: dict, updated_at_str: str
) -> None:
    """处理 POINTS 事件：写积分流水并同步余额快照。"""
    unique_id = str(_first(msg_obj, "unique_id") or "")
    mobile = str(_first(msg_obj, "mobile") or "")
    yz_open_id = str(_first(msg_obj, "yz_open_id", "yzOpenId") or "")
    if not unique_id:
        logger.warning("积分事件缺少 unique_id，跳过写入")
        return
    ledger_repo = PointsLedgerRepo(db)
    if await ledger_repo.get_by_unique_id(unique_id):
        logger.info("积分事件已处理，跳过: unique_id=%s", unique_id)
        return
    customer_id = await _resolve_customer_id(customer_repo, mobile, yz_open_id)
    await ledger_repo.insert(
        PointsLedgerEntry(
            unique_id=unique_id,
            amount=to_int(msg_obj.get("amount")),
            total=to_int(msg_obj.get("total")),
            event_type=str(msg_obj.get("event_type") or ""),
            source=LedgerSource.WEBHOOK,
            customer_id=customer_id,
            mobile=mobile,
            yz_open_id=yz_open_id,
            occurred_at=updated_at_str,
        )
    )
    if settings.POINTS_AUTHORITY != "local":
        await balance_repo.upsert_identity(
            mobile=mobile,
            customer_id=customer_id,
            yz_open_id=yz_open_id,
            points=to_int(msg_obj.get("total")),
        )


async def _handle_coupon_event(
    db, balance_repo, customer_repo, youzan_client, msg_obj: dict, updated_at_str: str
) -> None:
    """处理 COUPON_CUSTOMER_PROMOTION 事件：写优惠券库存记录并反查券详情。"""
    coupon_id = str(_first(msg_obj, "id", "coupon_id") or "")
    status = str(_first(msg_obj, "status") or "").upper()
    mobile = str(_first(msg_obj, "mobile") or "")
    coupon_group_id = str(_first(msg_obj, "coupon_group_id") or "")
    order_no = str(_first(msg_obj, "order_no") or "")
    if not coupon_id or not status:
        logger.warning("优惠券事件缺少 id 或 status，跳过写入")
        return
    inventory_repo = CouponInventoryRepo(db)
    if await inventory_repo.get_by_dedup_key(coupon_id, status, mobile):
        logger.info("优惠券事件已处理，跳过: coupon_id=%s status=%s", coupon_id, status)
        return
    detail = await YouzanMemberApi(youzan_client).get_coupon_group_detail(
        coupon_group_id
    )
    title, value_fen = _extract_coupon_detail(detail)
    tpl = parse_youzan_template(detail)
    await upsert_template_from_youzan(db, tpl)
    fields = extract_template_fields(msg_obj, detail)
    customer_id = await _resolve_customer_id(customer_repo, mobile, "")
    await inventory_repo.insert(
        CouponInventoryEntry(
            coupon_id=coupon_id,
            coupon_group_id=coupon_group_id,
            customer_id=customer_id,
            mobile=mobile,
            status=status,
            order_no=order_no,
            title=title,
            value_fen=value_fen,
            detail_json=json.dumps(detail, ensure_ascii=False),
            source=LedgerSource.WEBHOOK,
            occurred_at=updated_at_str,
            template_id=fields["template_id"],
            valid_from=fields["valid_from"],
            valid_until=fields["valid_until"],
        )
    )


async def _handle_customer_event(balance_repo, msg_obj: dict) -> None:
    """处理 SCRM_CUSTOMER_EVENT：更新客户身份与会员标记。"""
    mobile = str(_first(msg_obj, "mobile") or "")
    if not mobile:
        logger.warning("客户身份事件缺少 mobile，跳过写入")
        return
    await balance_repo.upsert_identity(
        mobile=mobile,
        display_name=str(_first(msg_obj, "name") or ""),
        is_member=1 if to_bool(msg_obj.get("is_member")) else 0,
    )


async def _handle_card_event(balance_repo, msg_obj: dict) -> None:
    """处理 SCRM_CUSTOMER_CARD：更新会员卡状态。"""
    mobile = str(_first(msg_obj, "mobile") or "")
    if not mobile:
        logger.warning("会员卡事件缺少 mobile，跳过写入")
        return
    await balance_repo.upsert_identity(
        mobile=mobile,
        yz_open_id=str(_first(msg_obj, "yz_open_id", "yzOpenId") or ""),
        card_alias=str(_first(msg_obj, "card_alias", "cardAlias") or ""),
        card_no=str(_first(msg_obj, "card_no", "cardNo") or ""),
        card_status=str(_first(msg_obj, "status") or ""),
        is_member=1 if str(_first(msg_obj, "status") or "") else 0,
    )


async def _resolve_customer_id(customer_repo, mobile: str, yz_open_id: str) -> str:
    """按手机号（有赞 openid 兜底）解析客户主档 ID。"""
    if mobile:
        masters = await customer_repo.get_by_phone(DEFAULT_TENANT_ID, mobile)
        if masters:
            return masters[0].id
    if yz_open_id:
        link = await customer_repo.get_identity_by_value(
            DEFAULT_TENANT_ID,
            CustomerIdentityType.MINIAPP_OPENID.value,
            yz_open_id,
        )
        if link is not None:
            return link.customer_id
    return ""


def _extract_coupon_detail(detail: dict) -> tuple[str, int]:
    """从优惠券模板详情中提取券名与面额（分）。"""
    if not detail:
        return "", 0
    group = detail.get("coupon_group")
    if not isinstance(group, dict):
        group = detail
    title = str(group.get("title") or group.get("name") or "")
    value = group.get("value") or group.get("amount") or group.get("coupon_value")
    return title, to_fen(value)


def _business_key(msg_obj: dict) -> str:
    """提取审计业务主键（mobile / openid / id / unique_id 依次兜底）。"""
    return str(
        _first(msg_obj, "mobile")
        or _first(msg_obj, "yz_open_id", "yzOpenId")
        or _first(msg_obj, "id", "coupon_id")
        or _first(msg_obj, "unique_id")
        or ""
    )


def _first(msg_obj: dict, *keys: str) -> object:
    """按 key 顺序取首个非空字段，兼容 snake_case 与 camelCase。"""
    for key in keys:
        value = msg_obj.get(key)
        if value not in (None, ""):
            return value
    return ""
