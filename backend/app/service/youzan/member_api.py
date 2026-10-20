"""有赞会员账务域 OpenAPI 子客户端（积分/优惠券/会员卡）。

复用 YouzanClient 的鉴权、重试与连接管理，不复制底层调用逻辑。

券/会员卡三个接口的名称、版本、请求参数与响应字段均按 **2026-10-20 生产
只读实测** 固定（有赞开放平台 API 目录 + 真实店铺响应），不得凭文档印象改动。
"""

from app.config import settings
from app.exceptions import APIError
from app.logger import setup_logger
from app.service.youzan.client import (
    build_gateway_error_message,
    extract_gateway_error,
)

logger = setup_logger()

# ── 有赞会员账务域 API 常量 ──────────────────────────────────────────────
# 说明：API 名称与版本来自有赞开放平台公开文档；真实店铺联调前需按实际开通的
# 应用权限验证，mock 模式下全部短路返回空数据。
POINTS_QUERY_API_NAME = "youzan.crm.customer.points.get"
# 版本必须是 1.0.0：3.0.0 会被有赞网关以 4005「非法的API」拒绝
# （2026-10-20 生产实测），调用结果恒为空字典，会让会员导入把积分锚点写成 0。
# 取数口径与生产实测脚本 `scripts/reconcile_youzan_points_dead_letters.py` 一致。
POINTS_QUERY_API_VERSION = "1.0.0"
# 有赞「查询客户当前积分」的 account_type：2 = 手机号。
POINTS_ACCOUNT_TYPE_MOBILE = 2

# 「查询买家优惠券列表」：有赞把买家券拆成优惠券（promocard）与优惠码
# （promocode）两个接口，版本固定 3.0.0。
# 2026-10-20 生产实测：旧常量 `youzan.ump.coupon.user.coupons` 在有赞开放平台
# API 目录中**并不存在**，任何版本（0.1.0~5.0.0）都被网关以 4005「非法的API」
# 拒绝，调用结果恒为空列表 → 会员导入漏券。
COUPON_LIST_API_NAME = "youzan.ump.promocard.buyer.search"
COUPON_LIST_API_VERSION = "3.0.0"
COUPON_CODE_LIST_API_NAME = "youzan.ump.promocode.buyer.search"
COUPON_CODE_LIST_API_VERSION = "3.0.0"
# 买家券状态枚举：VALID 有效（未使用）/ USED 已使用 / INVALID 已失效。
# 有赞按状态分别查询，各状态的返回集互相重叠（INVALID 的返回集包含 USED 的券），
# 必须三个状态全查并按券 ID 去重，否则漏券。2026-10-20 生产实测：同一客户
# VALID 返回 0 条、USED 返回 3 条、INVALID 返回 4 条。
COUPON_STATUS_VALID = "VALID"
COUPON_STATUS_USED = "USED"
COUPON_STATUS_INVALID = "INVALID"
COUPON_STATUS_VALUES = (
    COUPON_STATUS_VALID,
    COUPON_STATUS_USED,
    COUPON_STATUS_INVALID,
)

# 券模板详情：请求参数是 `id`（优惠活动 ID），**不是** `coupon_group_id`；
# 传错会被有赞判 161201012「id不能为null」并返回空模板。
COUPON_GROUP_DETAIL_API_NAME = "youzan.ump.coupon.detail.get"
COUPON_GROUP_DETAIL_API_VERSION = "3.0.0"

# 会员卡列表：分页参数是 `page`（**不是** `page_no`/`page_size`），传错会被判
# 141500101「分页数量不能小于1」；返回的会员卡列表在 `items` 字段。
MEMBER_CARD_LIST_API_NAME = "youzan.scrm.customer.card.list"
MEMBER_CARD_LIST_API_VERSION = "3.0.0"


class YouzanMemberApi:
    """会员账务域 API 子客户端。"""

    def __init__(self, youzan_client) -> None:
        self._client = youzan_client

    async def query_points(self, mobile: str) -> dict:
        """查询客户积分余额，返回原始响应 data/response 字典。

        查不到数据（空响应或接口报错）时返回空字典，**不得**伪造 0 积分：
        调用方据此判定「有赞侧未知」并跳过积分镜像，避免把「未知」写成 0
        清空会员已有的积分锚点。
        """
        if settings.YOUZAN_MOCK_MODE or not mobile:
            return {}
        result = await self._client.call_api(
            POINTS_QUERY_API_NAME,
            POINTS_QUERY_API_VERSION,
            _build_points_query_params(mobile),
        )
        data = _pick_dict(result)
        if not data:
            _log_points_query_miss(result)
            return {}
        return data

    async def list_customer_coupons(self, mobile: str) -> list[dict]:
        """拉取客户持有的全部优惠券与优惠码。

        有赞把买家券拆成 promocard（优惠券）与 promocode（优惠码）两个接口，
        且必须按 VALID/USED/INVALID 三种状态分别查询（三个返回集互相重叠，
        需按券 ID 去重合并）。返回的每条券带 `youzan_coupon_status` 标记其
        来源状态；**已失效且未使用**的券不返回——本地券账本没有「已过期」
        状态，把它写成可用券会让过期券被结算抵扣（资损）。

        网关级错误（如 4005「非法的API」）必须抛出：静默返回空列表会让
        会员导入把「接口失败」误判成「客户没有券」。
        """
        if settings.YOUZAN_MOCK_MODE or not mobile:
            return []
        merged: dict[str, dict] = {}
        for api_name, version in (
            (COUPON_LIST_API_NAME, COUPON_LIST_API_VERSION),
            (COUPON_CODE_LIST_API_NAME, COUPON_CODE_LIST_API_VERSION),
        ):
            for status in COUPON_STATUS_VALUES:
                result = await self._call_member_api(
                    api_name,
                    version,
                    {
                        "kdt_id": settings.YOUZAN_KDT_ID,
                        "mobile": mobile,
                        "status": status,
                    },
                )
                for coupon in _extract_coupon_items(result):
                    coupon_id = str(coupon.get("id") or coupon.get("coupon_id") or "")
                    if not coupon_id or coupon_id in merged:
                        continue
                    is_used = _safe_int(coupon.get("is_used")) == 1
                    if status == COUPON_STATUS_INVALID and not is_used:
                        # 已失效且未使用：本地没有「已过期」状态，且过期券不可用，
                        # 不落库以免被当成可用券。
                        continue
                    item = dict(coupon)
                    item["youzan_coupon_status"] = status
                    merged[coupon_id] = item
        logger.info("有赞客户优惠券拉取完成，共 %d 条", len(merged))
        return list(merged.values())

    async def get_coupon_group_detail(self, coupon_group_id: str) -> dict:
        """查询优惠券模板详情（Webhook 反查补全券名与面额）。

        请求参数是有赞的 `id`（优惠活动 ID），传 `coupon_group_id` 会被判
        161201012「id不能为null」，模板恒为空 → 券镜像没有面额与有效期。
        """
        if settings.YOUZAN_MOCK_MODE or not coupon_group_id:
            return {}
        try:
            result = await self._call_member_api(
                COUPON_GROUP_DETAIL_API_NAME,
                COUPON_GROUP_DETAIL_API_VERSION,
                {
                    "kdt_id": settings.YOUZAN_KDT_ID,
                    "id": coupon_group_id,
                },
            )
        except APIError as exc:
            logger.error(
                "有赞优惠券模板详情反查被网关拒绝: coupon_group_id=%s err=%s",
                coupon_group_id,
                exc,
            )
            return {}
        except Exception as exc:
            logger.warning(
                "有赞优惠券模板详情反查失败: coupon_group_id=%s err=%s",
                coupon_group_id,
                exc,
            )
            return {}
        _log_member_api_business_error(COUPON_GROUP_DETAIL_API_NAME, result)
        return _pick_dict(result)

    async def list_customer_cards(self, mobile: str) -> list[dict]:
        """拉取客户会员卡列表。

        分页参数是有赞的 `page`（不是 `page_no`/`page_size`），会员卡列表在
        响应的 `items` 字段。网关级错误必须抛出，避免把接口失败当成「无卡」。
        """
        if settings.YOUZAN_MOCK_MODE or not mobile:
            return []
        result = await self._call_member_api(
            MEMBER_CARD_LIST_API_NAME,
            MEMBER_CARD_LIST_API_VERSION,
            {
                "kdt_id": settings.YOUZAN_KDT_ID,
                "mobile": mobile,
                "page": 1,
            },
        )
        response = _pick_dict(result)
        cards = response.get("items")
        if not isinstance(cards, list):
            return []
        return [card for card in cards if isinstance(card, dict)]

    async def _call_member_api(self, api_name: str, version: str, params: dict) -> dict:
        """调用有赞会员域 API；网关级错误必须抛出，不得静默当成空数据。

        有赞网关拒绝调用时响应体没有业务 `data`，只有 `gw_err_resp`：
        1.0.0/2.0.0 等错误版本会返回 4005「非法的API」。若按空列表处理，
        会员导入会把「接口被拒」误判成「客户没有券/没有卡」，造成漏采。
        """
        result: dict = await self._client.call_api(api_name, version, params)
        gateway = extract_gateway_error(result)
        if gateway is None:
            return result
        message = build_gateway_error_message(api_name, gateway)
        logger.error("%s", message)
        raise APIError(message)


def _build_points_query_params(mobile: str) -> dict:
    """构造「查询客户当前积分」的请求体。

    形状与生产实测脚本（`scripts/reconcile_youzan_points_dead_letters.py`）
    完全一致：手机号放在 `user.account_id`，`user.account_type=2` 表示手机号；
    积分余额从响应的 `data.point` 读取。店铺身份由 access_token 绑定，
    因此请求体不再额外携带 `kdt_id`（与实测脚本保持一致，避免多传字段
    被有赞判为非法参数）。
    """
    return {
        "user": {
            "account_type": POINTS_ACCOUNT_TYPE_MOBILE,
            "account_id": mobile,
        },
        "is_do_extpoint": False,
        "is_query_points_account_version": False,
        "need_expired_but_not_executed": False,
    }


def _log_points_query_miss(result: dict) -> None:
    """积分查询没拿到业务数据时记录原因，区分「查不到」与「确实是 0 分」。"""
    gateway = extract_gateway_error(result)
    if gateway is not None:
        logger.error(
            "有赞积分查询被网关拒绝: %s",
            build_gateway_error_message(POINTS_QUERY_API_NAME, gateway),
        )
        return
    logger.error(
        "有赞积分查询未返回业务数据: keys=%s",
        sorted(result.keys()) if isinstance(result, dict) else "not_object",
    )


def _log_member_api_business_error(api_name: str, result: dict) -> None:
    """有赞业务错误码（HTTP 200 但 success=false）必须留痕，不能当成空数据。"""
    if not isinstance(result, dict):
        return
    if result.get("success") is True:
        return
    code = result.get("code")
    if code is None or str(code) == "200":
        return
    logger.warning(
        "有赞会员域接口返回业务错误: api=%s code=%s message=%s",
        api_name,
        code,
        result.get("message"),
    )


def _extract_coupon_items(result: dict) -> list[dict]:
    """从有赞响应中提取买家券列表。

    `youzan.ump.promocard.buyer.search` / `promocode.buyer.search` 3.0.0 的
    `data` **直接是数组**（2026-10-20 生产实测），不是 `{cards: [...]}` 结构；
    两种形状都要兼容，避免响应形状变化时把券整批漏掉。
    """
    for container in (result.get("data"), result.get("response")):
        if isinstance(container, list):
            return [item for item in container if isinstance(item, dict)]
        if not isinstance(container, dict):
            continue
        for key in ("cards", "codes", "coupons", "list"):
            items = container.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
    return []


def _pick_dict(result: dict) -> dict:
    """从有赞响应中提取 data 或 response 字典。"""
    data = result.get("data") or result.get("response") or {}
    return data if isinstance(data, dict) else {}


def _safe_int(value) -> int:
    """容忍转换整数，失败返回 0。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
