"""有赞会员账务域 OpenAPI 子客户端（积分/优惠券/会员卡）。

复用 YouzanClient 的鉴权、重试与连接管理，不复制底层调用逻辑。
"""

from app.config import settings
from app.logger import setup_logger

logger = setup_logger()

# ── 有赞会员账务域 API 常量 ──────────────────────────────────────────────
# 说明：API 名称与版本来自有赞开放平台公开文档；真实店铺联调前需按实际开通的
# 应用权限验证，mock 模式下全部短路返回空数据。
POINTS_QUERY_API_NAME = "youzan.crm.customer.points.get"
POINTS_QUERY_API_VERSION = "3.0.0"
COUPON_LIST_API_NAME = "youzan.ump.coupon.user.coupons"
COUPON_LIST_API_VERSION = "3.0.0"
COUPON_GROUP_DETAIL_API_NAME = "youzan.ump.coupon.detail.get"
COUPON_GROUP_DETAIL_API_VERSION = "3.0.0"
MEMBER_CARD_LIST_API_NAME = "youzan.scrm.customer.card.list"
MEMBER_CARD_LIST_API_VERSION = "3.0.0"

MEMBER_API_PAGE_SIZE = 50


class YouzanMemberApi:
    """会员账务域 API 子客户端。"""

    def __init__(self, youzan_client) -> None:
        self._client = youzan_client

    async def query_points(self, mobile: str) -> dict:
        """查询客户积分余额，返回原始响应 data/response 字典。"""
        if settings.YOUZAN_MOCK_MODE or not mobile:
            return {}
        result = await self._client.call_api(
            POINTS_QUERY_API_NAME,
            POINTS_QUERY_API_VERSION,
            {"kdt_id": settings.YOUZAN_KDT_ID, "mobile": mobile},
        )
        return _pick_dict(result)

    async def list_customer_coupons(self, mobile: str) -> list[dict]:
        """分页拉取客户优惠券列表。"""
        if settings.YOUZAN_MOCK_MODE or not mobile:
            return []
        page_no = 1
        all_coupons: list[dict] = []
        while True:
            result = await self._client.call_api(
                COUPON_LIST_API_NAME,
                COUPON_LIST_API_VERSION,
                {
                    "kdt_id": settings.YOUZAN_KDT_ID,
                    "mobile": mobile,
                    "status": "",
                    "page_no": page_no,
                    "page_size": MEMBER_API_PAGE_SIZE,
                },
            )
            response = _pick_dict(result)
            coupons = response.get("coupons") or response.get("list") or []
            if not isinstance(coupons, list) or not coupons:
                break
            all_coupons.extend(coupons)
            total_count = _safe_int(
                response.get("total") or response.get("total_count")
            )
            if total_count > 0 and page_no * MEMBER_API_PAGE_SIZE >= total_count:
                break
            page_no += 1
        logger.info("有赞客户优惠券拉取完成，共 %d 条", len(all_coupons))
        return all_coupons

    async def get_coupon_group_detail(self, coupon_group_id: str) -> dict:
        """查询优惠券模板详情（Webhook 反查补全券名与面额）。"""
        if settings.YOUZAN_MOCK_MODE or not coupon_group_id:
            return {}
        try:
            result = await self._client.call_api(
                COUPON_GROUP_DETAIL_API_NAME,
                COUPON_GROUP_DETAIL_API_VERSION,
                {
                    "kdt_id": settings.YOUZAN_KDT_ID,
                    "coupon_group_id": coupon_group_id,
                },
            )
        except Exception as exc:
            logger.warning(
                "有赞优惠券模板详情反查失败: coupon_group_id=%s err=%s",
                coupon_group_id,
                exc,
            )
            return {}
        return _pick_dict(result)

    async def list_customer_cards(self, mobile: str) -> list[dict]:
        """拉取客户会员卡列表。"""
        if settings.YOUZAN_MOCK_MODE or not mobile:
            return []
        result = await self._client.call_api(
            MEMBER_CARD_LIST_API_NAME,
            MEMBER_CARD_LIST_API_VERSION,
            {"kdt_id": settings.YOUZAN_KDT_ID, "mobile": mobile},
        )
        response = _pick_dict(result)
        cards = (
            response.get("cards")
            or response.get("list")
            or response.get("card_list")
            or []
        )
        return cards if isinstance(cards, list) else []


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
