"""有赞 webhook 辅助函数合同测试。"""

from app.api.integrations.webhook_helpers import extract_business_fields
from app.models.youzan_webhook_event import YouzanWebhookBusinessType


def test_extract_business_fields_uses_canonical_item_parser() -> None:
    business_type, business_key = extract_business_fields(
        {"id": "5001001"},
        "item_info",
        "",
    )

    assert business_type == YouzanWebhookBusinessType.ITEM
    assert business_key == "5001001"
