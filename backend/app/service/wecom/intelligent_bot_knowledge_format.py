"""企微智能机器人知识库展示格式。"""

from typing import Any

from app.service.wecom.intelligent_bot_tool_format import knowledge_line

DELIVERY_QUESTION_KEYWORDS = ("配送", "送", "送达", "发货", "物流")
REFUND_QUESTION_KEYWORDS = ("退款", "退单", "售后", "退货")
DELIVERY_KNOWLEDGE_FALLBACK = (
    "配送安排以门店实际排期为准，不要承诺一定准时送达。\n"
    "员工可复制回复：亲，可以先帮您确认配送安排。配送范围、配送费和可配送时段"
    "需要按下单商品、地址区域和门店当天排期核实，时间敏感或超出常规范围的需求"
    "我会帮您转人工确认后再回复。\n"
    "下一步：先收集客户期望配送时间、地址区域和联系方式；急单、指定准确送达时间"
    "或疑似超区需求转人工确认。"
)
REFUND_KNOWLEDGE_FALLBACK = (
    "退款/售后规则需要先按订单状态、商品是否制作、是否发货和后台售后记录核实，"
    "不要直接承诺可退金额或到账时间。\n"
    "员工可复制回复：亲，退款/售后我先帮您核实订单状态和制作进度。"
    "如果还未制作或未发货，会按门店规则尽快确认处理；如果已经制作、配送中"
    "或涉及商品问题，需要结合现场记录和后台售后状态人工确认后再回复。\n"
    "下一步：先查订单和售后记录；金额、时效或争议场景转人工确认。"
)


def knowledge_answer_text(question: str, sources: list[dict[str, Any]]) -> str:
    """格式化员工可读知识库回复。"""
    if sources:
        return "\n".join(knowledge_line(item) for item in sources)
    if _is_delivery_question(question):
        return DELIVERY_KNOWLEDGE_FALLBACK
    if _is_refund_question(question):
        return REFUND_KNOWLEDGE_FALLBACK
    return "未找到匹配知识。"


def _is_delivery_question(question: str) -> bool:
    return any(keyword in question for keyword in DELIVERY_QUESTION_KEYWORDS)


def _is_refund_question(question: str) -> bool:
    return any(keyword in question for keyword in REFUND_QUESTION_KEYWORDS)
