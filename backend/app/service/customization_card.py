"""定制蛋糕结构化需求卡服务。

本服务只做“需求收集 + 文本化”：校验顾客诉求并产出可复制的需求卡，
**不写数据库、不创建订单、不扣款、不占用预约时段**。
顾客端 AI 工具与小程序 API 共用同一套校验口径，避免导购口径与下单口径漂移。
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from app.service.order.fulfillment_dual_track import (
    OrderFulfillmentDualTrackService,
)

# 未指定甜度时的门店默认甜度。
DEFAULT_SWEETNESS = "8分甜"
# 需求卡文本字段统一长度上限，防止超长内容污染对话上下文。
MAX_FIELD_LENGTH = 200
# 备注长度上限，与门店人工记录习惯保持一致。
REMARK_MAX_LENGTH = 200
# 摘要占位文案：顾客未确定的要素显式标注，避免店员误认为已确认。
PENDING_FIELD_TEXT = "待确认"
EMPTY_FIELD_TEXT = "无"

# 必填项中文名称，用于生成可读的校验错误信息。
REQUIRED_FIELD_LABELS = {
    "size": "尺寸规格",
    "filling": "夹心口味",
    "greeting": "祝福语",
    "accessories": "配件",
}

# 甜度口语写法归一表：把常见口语统一成门店可识别的标准表述。
SWEETNESS_ALIASES = {
    "3分": "3分甜",
    "3分甜": "3分甜",
    "三分": "3分甜",
    "三分甜": "3分甜",
    "5分": "5分甜",
    "5分甜": "5分甜",
    "五分": "5分甜",
    "五分甜": "5分甜",
    "8分": "8分甜",
    "8分甜": "8分甜",
    "八分": "8分甜",
    "八分甜": "8分甜",
    "木糖醇": "木糖醇",
}


@dataclass(frozen=True)
class CustomizationCard:
    """定制蛋糕结构化需求卡（只读产物，不落库）。"""

    size: str
    filling: str
    sweetness: str
    greeting: str
    accessories: str
    expect_time: str
    remark: str
    summary: str

    def to_dict(self) -> dict[str, str]:
        """转成对外 JSON 契约字段，与小程序接口、AI 工具返回保持一致。"""
        return {
            "size": self.size,
            "filling": self.filling,
            "sweetness": self.sweetness,
            "greeting": self.greeting,
            "accessories": self.accessories,
            "expectTime": self.expect_time,
            "remark": self.remark,
            "summary": self.summary,
        }


class CustomizationCardService:
    """生成并校验定制蛋糕需求卡，不产生任何交易副作用。"""

    def __init__(self, now_provider: Callable[[], datetime] | None = None) -> None:
        # 复用双轨履约的提前预约校验，保证导购口径与真实下单口径一致。
        self._fulfillment_service = OrderFulfillmentDualTrackService(
            now_provider=now_provider
        )

    def build_card(self, payload: dict) -> dict:
        """校验顾客诉求并生成结构化需求卡字典。"""
        if not isinstance(payload, dict):
            raise ValueError("定制需求卡参数格式无效")
        size = self._require_field(payload, "size")
        filling = self._require_field(payload, "filling")
        greeting = self._require_field(payload, "greeting")
        accessories = self._require_field(payload, "accessories")
        sweetness = self._normalize_sweetness(payload.get("sweetness"))
        expect_time = self._normalize_expect_time(payload)
        remark = self._normalize_remark(payload.get("remark"))
        card = CustomizationCard(
            size=size,
            filling=filling,
            sweetness=sweetness,
            greeting=greeting,
            accessories=accessories,
            expect_time=expect_time,
            remark=remark,
            summary="",
        )
        return {**card.to_dict(), "summary": self._build_summary(card)}

    def _require_field(self, payload: dict, key: str) -> str:
        """读取必填文本字段，缺失时抛出中文错误。"""
        label = REQUIRED_FIELD_LABELS[key]
        value = _to_text(payload.get(key))
        if not value:
            raise ValueError(f"定制需求卡必须填写{label}")
        if len(value) > MAX_FIELD_LENGTH:
            raise ValueError(f"定制需求卡{label}不能超过{MAX_FIELD_LENGTH}字")
        return value

    def _normalize_sweetness(self, value: object) -> str:
        """归一甜度表达；未指定时按门店默认甜度处理。"""
        text = _to_text(value)
        if not text:
            return DEFAULT_SWEETNESS
        if len(text) > MAX_FIELD_LENGTH:
            raise ValueError(f"定制需求卡甜度不能超过{MAX_FIELD_LENGTH}字")
        return SWEETNESS_ALIASES.get(text, text)

    def _normalize_expect_time(self, payload: dict) -> str:
        """校验预约时间；未提供时返回空串表示“时间待人工确认”。"""
        raw = _to_text(payload.get("expectTime") or payload.get("expect_time"))
        if not raw:
            return ""
        # 双轨履约服务同时负责格式校验与“至少提前 4 小时”的预约规则。
        self._fulfillment_service.validate_advance_hours(raw)
        return raw

    def _normalize_remark(self, value: object) -> str:
        """校验备注长度，超限直接拒绝。"""
        text = _to_text(value)
        if len(text) > REMARK_MAX_LENGTH:
            raise ValueError(f"定制需求卡备注不能超过{REMARK_MAX_LENGTH}字")
        return text

    def _build_summary(self, card: CustomizationCard) -> str:
        """生成可复制给店员的纯文本摘要，七个要素固定成栏，便于店员逐项核对。"""
        lines = [
            f"尺寸：{card.size}",
            f"夹心：{card.filling}",
            f"甜度：{card.sweetness}",
            f"祝福语：{card.greeting}",
            f"配件：{card.accessories}",
            f"预约时间：{card.expect_time or PENDING_FIELD_TEXT}",
            f"备注：{card.remark or EMPTY_FIELD_TEXT}",
        ]
        return "定制蛋糕需求卡\n" + "\n".join(lines)


def _to_text(value: object) -> str:
    """把任意入参规整成去除首尾空白的文本。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


__all__ = [
    "CustomizationCard",
    "CustomizationCardService",
    "DEFAULT_SWEETNESS",
    "EMPTY_FIELD_TEXT",
    "MAX_FIELD_LENGTH",
    "PENDING_FIELD_TEXT",
    "REMARK_MAX_LENGTH",
]
