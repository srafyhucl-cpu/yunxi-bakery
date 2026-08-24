from enum import IntEnum


class IntentType(IntEnum):
    PRODUCT_CONSULTATION = 1
    STORE_POLICY = 2
    SHIPPING_FEE = 3
    DELIVERY_SCHEDULE = 4
    ORDER_SERVICE = 5
    AFTER_SALES_ISSUE = 6
    HUMAN_ASSISTANCE = 7
    SMALL_TALK = 8


INTENT_LABELS = {
    IntentType.PRODUCT_CONSULTATION: "商品咨询",
    IntentType.STORE_POLICY: "规则咨询",
    IntentType.SHIPPING_FEE: "运费费用",
    IntentType.DELIVERY_SCHEDULE: "配送履约",
    IntentType.ORDER_SERVICE: "订单办理",
    IntentType.AFTER_SALES_ISSUE: "售后异常",
    IntentType.HUMAN_ASSISTANCE: "人工服务",
    IntentType.SMALL_TALK: "闲聊其他",
}

TRANSFER_REQUIRED_INTENTS = {
    IntentType.ORDER_SERVICE,
    IntentType.AFTER_SALES_ISSUE,
    IntentType.HUMAN_ASSISTANCE,
}

INTENT_ID_CHARACTERS = tuple(str(int(intent)) for intent in IntentType)


def is_transfer_intent(intent: IntentType) -> bool:
    return intent in TRANSFER_REQUIRED_INTENTS
