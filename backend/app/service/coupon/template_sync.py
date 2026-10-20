"""券模板解析与本地同步回填。"""

from app.models.coupon import CouponTemplate, CouponType
from app.repository.coupon_template_repo import CouponTemplateRepo
from app.utils import format_millis_date, yuan_to_fen

# 有赞券优惠属性（`preferential_type`）：1=优惠（代金/满减）2=折扣
# 5=运费抵扣券（抵的是运费而非商品金额），3=指定商品兑换券。
# 本店 21 个券模板的分布（2026-10-20 生产实测）：1 → 12 个、5 → 1 个、3 → 8 个，
# 没有 2（折扣券）实例。
YOZAN_PREFERENTIAL_CASH = 1
YOZAN_PREFERENTIAL_DISCOUNT = 2


def parse_youzan_template(detail: dict) -> CouponTemplate:
    """从有赞券详情解析模板字段；详情缺失时返回默认模板。

    有赞 `youzan.ump.coupon.detail.get` 3.0.0 返回的是**扁平** CouponGroup
    （2026-10-20 生产实测，店铺 32035241「20元优惠卷」）：
    - `denominations`：面额，单位**分**（20 元券 = 2000）
    - `condition`：满额条件，单位**分**（满 50 元 = 5000）
    - `preferential_type`：1=优惠（代金/满减）2=折扣 3=指定商品兑换券
      5=运费抵扣券
    - `valid_start_time` / `valid_end_time`：**毫秒**时间戳

    历史文本形状（`threshold`/`value` 单位为元）继续兼容。
    """
    if not isinstance(detail, dict) or not detail:
        return CouponTemplate(id="", name="", coupon_type="")
    group = (
        detail.get("coupon_group")
        if isinstance(detail.get("coupon_group"), dict)
        else detail
    )
    coupon_type = _parse_coupon_type(group)
    threshold = _parse_threshold_fen(group)
    value = _parse_value_fen(group)
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
    """从客户券行 + 详情提取 coupon_inventory 回填字段。

    券的有效期必须优先取**券自身**的 `valid_start_at` / `expire_at`（毫秒）：
    有赞「领券后 N 天有效」型券模板的 `valid_start_time` / `valid_end_time`
    描述的是活动有效期（实测为 2024-09-26 ~ 2100-01-01），拿模板有效期判券
    会放过已过期券（资损）。
    """
    tpl = parse_youzan_template(detail)
    valid_from = format_millis_date(coupon.get("valid_start_at")) or tpl.valid_from
    valid_until = format_millis_date(coupon.get("expire_at")) or tpl.valid_until
    return {
        "template_id": tpl.id,
        "valid_from": valid_from,
        "valid_until": valid_until,
    }


async def upsert_template_from_youzan(
    db, template: CouponTemplate, repo: CouponTemplateRepo | None = None
) -> None:
    """把有赞模板 upsert 进本地表（模板 ID 为空时跳过）。"""
    if not template.id:
        return
    repo = repo or CouponTemplateRepo(db)
    await repo.upsert_from_youzan(template)


def _parse_coupon_type(group: dict) -> str:
    """推导本地券类型。

    有赞 `preferential_type`：1=优惠（代金/满减），2=折扣，3=指定商品兑换券，
    5=运费抵扣券。后两类抵的不是商品金额（运费 / 指定商品），本地券引擎没有
    对应语义；映射不出时返回空字符串（券会被本地引擎判为不可用，而不是按
    错误金额抵扣）。
    """
    legacy = str(group.get("coupon_type") or "").upper()
    if legacy in (
        CouponType.FULL_REDUCTION,
        CouponType.NO_THRESHOLD,
        CouponType.DISCOUNT,
    ):
        return legacy
    preferential_type = _to_int(group.get("preferential_type"))
    if preferential_type == YOZAN_PREFERENTIAL_DISCOUNT:
        return CouponType.DISCOUNT
    if preferential_type != YOZAN_PREFERENTIAL_CASH:
        return ""
    threshold = _to_int(group.get("condition"))
    return CouponType.FULL_REDUCTION if threshold > 0 else CouponType.NO_THRESHOLD


def _parse_threshold_fen(group: dict) -> int:
    """满额门槛（分）：有赞 `condition` 单位为分，旧形状 `threshold` 单位为元。"""
    condition = group.get("condition")
    if condition is not None and condition != "":
        return _to_int(condition)
    return yuan_to_fen(group.get("threshold") or group.get("threshold_amount") or 0)


def _parse_value_fen(group: dict) -> int:
    """面额（分）：有赞 `denominations` 单位为分，旧形状 `value` 单位为元。"""
    denominations = group.get("denominations")
    if denominations is not None and denominations != "":
        return _to_int(denominations)
    return yuan_to_fen(
        group.get("value") or group.get("amount") or group.get("coupon_value") or 0
    )


def _parse_discount_bp(raw: object) -> int:
    """解析折扣为应付比例万分比（discount_bp）。

    有赞券详情的 `discount` 字段口径（官方文档：折扣 88 = 8.8折）：
    - 1 <= v < 10 按折数：9（9折）-> 9000，9.5 -> 9500
    - 10 <= v 按百分比：88（8.8折）-> 8800
    - 0 < v < 1 按折扣率小数：0.9（90%）-> 9000
    - 空/0/无法解析 -> 0
    """
    if raw in (None, "", 0, "0", "0.0"):
        return 0
    value = float(str(raw))
    if 0 < value < 1:
        return int(round(value * 10000))
    if 1 <= value < 10:
        return int(round(value * 1000))
    if value >= 10:
        return int(round(value * 100))
    return 0


def _parse_valid_range(group: dict) -> tuple[str, str]:
    """从详情提取有效期（取日期部分）。

    有赞返回的是毫秒时间戳（1727341443000），必须按北京时间换算后再取日期；
    直接截断字符串会得到无意义数字。
    """
    valid_from = format_millis_date(
        group.get("valid_start_time") or group.get("start_time")
    )
    valid_until = format_millis_date(
        group.get("valid_end_time") or group.get("end_time")
    )
    return valid_from, valid_until


def _to_int(value: object) -> int:
    """容忍转换整数（支持字符串/浮点），失败返回 0。"""
    if value is None:
        return 0
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return 0
