"""有赞券模板解析与本地同步回填。"""

from app.models.coupon import CouponTemplate
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.utils import yuan_to_fen


def parse_youzan_template(detail: dict) -> CouponTemplate:
    """从有赞券详情解析模板字段；详情缺失时返回默认模板。

    金额字段（threshold/value/cap）按有赞详情返回的元单位换算为分。
    """
    if not isinstance(detail, dict) or not detail:
        return CouponTemplate(id="", name="", coupon_type="")
    group = (
        detail.get("coupon_group")
        if isinstance(detail.get("coupon_group"), dict)
        else detail
    )
    coupon_type = str(group.get("coupon_type") or "").upper()
    if coupon_type not in ("FULL_REDUCTION", "NO_THRESHOLD", "DISCOUNT"):
        coupon_type = ""
    threshold = yuan_to_fen(
        group.get("threshold") or group.get("threshold_amount") or 0
    )
    value = yuan_to_fen(
        group.get("value") or group.get("amount") or group.get("coupon_value") or 0
    )
    discount_bp = _parse_discount_bp(group.get("discount"))
    cap = yuan_to_fen(group.get("cap") or group.get("discount_limit") or 0)
    valid_from, valid_until = _parse_valid_range(group)
    return CouponTemplate(
        id=str(group.get("coupon_group_id") or group.get("id") or ""),
        name=str(group.get("title") or group.get("name") or ""),
        coupon_type=coupon_type,
        threshold_fen=threshold,
        value_fen=value,
        discount_bp=discount_bp,
        cap_fen=cap,
        valid_from=valid_from,
        valid_until=valid_until,
        source="youzan",
    )


def extract_template_fields(coupon: dict, detail: dict) -> dict:
    """从客户券行 + 详情提取 coupon_inventory 回填字段。"""
    tpl = parse_youzan_template(detail)
    return {
        "template_id": tpl.id,
        "valid_from": tpl.valid_from,
        "valid_until": tpl.valid_until,
    }


async def upsert_template_from_youzan(
    db, template: CouponTemplate, repo: CouponTemplateRepo | None = None
) -> None:
    """把有赞模板 upsert 进本地表（模板 ID 为空时跳过）。"""
    if not template.id:
        return
    repo = repo or CouponTemplateRepo(db)
    await repo.upsert_from_youzan(template)


def _parse_discount_bp(raw: object) -> int:
    """解析折扣为应付比例万分比（discount_bp）。

    约定（有赞真实字段联调时校准）：
    - 1 <= v < 10 按折数：9（9折）-> 9000，9.5 -> 9500
    - 0 < v < 1 按折扣率小数：0.9（90%）-> 9000
    - 空/0/无法解析（如 >= 10 的百分比歧义输入）-> 0
    """
    if raw in (None, "", 0, "0", "0.0"):
        return 0
    value = float(str(raw))
    if 0 < value < 1:
        return int(round(value * 10000))
    if 1 <= value < 10:
        return int(round(value * 1000))
    return 0


def _parse_valid_range(group: dict) -> tuple[str, str]:
    """从详情提取有效期（取日期部分）。"""
    valid_from = str(group.get("valid_start_time") or group.get("start_time") or "")
    valid_until = str(group.get("valid_end_time") or group.get("end_time") or "")
    return valid_from[:10], valid_until[:10]
