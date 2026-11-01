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


TRANSFER_REQUIRED_INTENTS = {
    IntentType.ORDER_SERVICE,
    IntentType.AFTER_SALES_ISSUE,
    IntentType.HUMAN_ASSISTANCE,
}

INTENT_ID_CHARACTERS = tuple(str(int(intent)) for intent in IntentType)


def is_transfer_intent(intent: IntentType) -> bool:
    return intent in TRANSFER_REQUIRED_INTENTS
