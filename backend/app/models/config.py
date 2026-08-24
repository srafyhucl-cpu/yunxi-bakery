"""
店铺运营配置数据模型。

管理可由后台动态调整的运营参数（如主推款列表等）。
"""

from dataclasses import dataclass

FEATURED_PRODUCTS_KEY = "featured_products"
SHOP_OPERATIONS_KEY = "shop_operations"
SHOP_PAGE_DRAFT_PREFIX = "shop_page_draft:"
SHOP_PAGE_PUBLISHED_PREFIX = "shop_page_published:"

DEFAULT_SHOP_OPERATIONS = {
    "shopName": "芸熙烘焙",
    "customerWechat": "13240240418",
    "customerPhone": "13240240418",
    "businessHours": "09:00-20:00",
    "pickupAddress": "门店自提，具体地址请联系客服确认",
    "deliveryNotice": "门店配送需提前预约，配送范围和费用以客服确认为准",
    "pickupNotice": "蛋糕建议提前 24 小时预订，到店自提前请确认取货时间",
    "paymentMode": "mock",
    "privacyPolicyTitle": "隐私政策",
    "privacyPolicyContent": "我们仅在下单、配送、客服和售后所必需的范围内收集联系人、手机号、地址、订单备注等信息，并用于完成蛋糕预订、履约通知和售后服务。未经用户授权，不会将个人信息用于无关用途。",
    "userAgreementTitle": "用户协议",
    "userAgreementContent": "用户在芸熙烘焙小程序下单前，应确认商品规格、取货或配送时间、联系人和备注信息。定制蛋糕请提前与客服确认可制作内容；订单提交后如需修改，请尽快联系客服处理。",
    "afterSalesPolicyTitle": "售后说明",
    "afterSalesPolicyContent": "蛋糕属于即时制作食品，请在约定时间取货或收货。若出现配送破损、商品错漏或质量问题，请保留照片和订单信息并第一时间联系客服，我们会按实际情况协助补救、重做或退款。",
}


@dataclass
class ShopConfig:
    """一条店铺配置记录。"""

    key: str
    value: str
    updated_at: str = ""
