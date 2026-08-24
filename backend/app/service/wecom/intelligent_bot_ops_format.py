"""企微智能机器人运营工具展示格式化。"""

import re
from typing import Any

from app.service.wecom.intelligent_bot_tool_format import mask_phone, snippet
from app.service.wecom.ump import parse_ump_tags

ADDRESS_PREVIEW_LENGTH = 4
IDENTIFIER_PREFIX_LENGTH = 4
IDENTIFIER_SUFFIX_LENGTH = 4
TRANSFER_ID_SUFFIX_LENGTH = 5
OPS_STATUS_LABELS = {
    "ok": "系统状态正常",
    "attention": "系统需要关注",
    "unknown": "系统状态未知",
}
OFFLINE_REVIEW_SKIPPED_REASON_LABELS = {
    "outside_night_window": "当前不在夜间复盘窗口，最近一轮没有执行",
    "not_run": "最近一轮还没有执行记录",
}
OFFLINE_REVIEW_SKIPPED_FALLBACK = "最近一轮没有执行，原因需到后台调度日志确认"
OFFLINE_REVIEW_SKIPPED_NEXT_ACTION = (
    "如需立即复盘，请确认离线复盘开关和夜间执行窗口；否则等夜间任务自动运行后再查看。"
)
OFFLINE_REVIEW_COMPLETED_NEXT_ACTION = (
    "可根据质检、知识缺口和客户记忆数量继续追踪异常会话。"
)
PHONE_PATTERN = re.compile(r"1[3-9]\d{9}")
ADDRESS_PATTERN = re.compile(r"[\u4e00-\u9fa5A-Za-z0-9]{1,16}[路街道巷弄]\s*\d+\s*号?")
DANGLING_UMP_PATTERN = re.compile(r"\s*\[UMP:\s*.*$", re.DOTALL)


def compact_address(address: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(address.get("id", "")),
        "receiverName": str(address.get("receiverName", "")),
        "receiverPhoneMasked": mask_phone(str(address.get("receiverPhone", ""))),
        "addressPreview": mask_address(str(address.get("address", ""))),
        "isDefault": bool(address.get("isDefault", False)),
        "updatedAt": str(address.get("updatedAt", "")),
    }


def compact_transfer(transfer: Any) -> dict[str, Any]:
    return {
        "id": str(getattr(transfer, "id", "")),
        "sessionId": str(getattr(transfer, "session_id", "")),
        "userRef": mask_identifier(str(getattr(transfer, "user_id", ""))),
        "reason": str(getattr(transfer, "reason", "")),
        "summaryPreview": redact_sensitive_text(
            str(getattr(transfer, "conversation_summary", ""))
        ),
        "createdAt": str(getattr(transfer, "created_at", "")),
    }


def compact_group_followup(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id", "")),
        "customerName": str(item.get("customerName", "")),
        "customerPhoneMasked": mask_phone(str(item.get("customerPhone", ""))),
        "productName": str(item.get("productName", "")),
        "quantity": int(item.get("quantity", 0) or 0),
        "fulfillmentMethod": str(item.get("fulfillmentMethod", "")),
        "desiredTime": str(item.get("desiredTime", "")),
        "addressPreview": mask_address(str(item.get("address", ""))),
        "remarkPreview": redact_sensitive_text(str(item.get("remark", ""))),
        "status": str(item.get("status", "")),
    }


def compact_webhook(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "eventType": str(item.get("event_type", "")),
        "businessKey": str(item.get("business_key", "")),
        "errorType": str(item.get("error_type", "")),
        "errorMessagePreview": redact_sensitive_text(
            str(item.get("error_message", ""))
        ),
    }


def address_line(address: dict[str, Any]) -> str:
    default_label = "默认" if address["isDefault"] else "非默认"
    return (
        f"{address['receiverName']}｜{address['receiverPhoneMasked']}｜"
        f"{default_label}｜{address['addressPreview']}"
    )


def group_summary_line(summary: dict[str, Any]) -> str:
    campaign = summary.get("campaign", {})
    return (
        f"{campaign.get('title', '客户群批次')}："
        f"{summary.get('totalRegistrations', 0)} 人登记，"
        f"合计 {summary.get('totalQuantity', 0)} 份。"
    )


def customer_lookup_empty_line(query: str) -> str:
    query_preview = customer_lookup_query_preview(query)
    if query_preview:
        return f"没找到“{query_preview}”的客户地址线索。"
    return "没找到匹配的客户地址线索。"


def customer_lookup_empty_next_action() -> str:
    return "请换客户姓名或地址关键词再查；如果是新客户，先让客户补充收货信息。"


def customer_lookup_query_preview(query: str) -> str:
    return _safe_lookup_query_preview(query)


def group_campaign_missing_line(campaign_id: str) -> str:
    clean_campaign_id = campaign_id.strip()
    if clean_campaign_id:
        return f"未找到客户群活动批次 campaignId:{clean_campaign_id}。"
    return "未找到客户群活动批次。"


def group_campaign_missing_next_action() -> str:
    return "请确认 campaignId 是否复制完整；如果只知道群名或活动标题，先到后台客户群活动列表查对应批次。"


def transfer_line(item: dict[str, Any]) -> str:
    line = f"工单尾号 {short_identifier(item['id'])}｜{item['reason'] or '未填写原因'}"
    summary_preview = str(item.get("summaryPreview", "") or "")
    if summary_preview:
        line += f"｜摘要：{summary_preview}"
    return line


def ops_summary_line(summary: dict[str, Any]) -> str:
    counts = summary.get("counts", {})
    status = str(summary.get("status", "unknown") or "unknown")
    status_label = OPS_STATUS_LABELS.get(status, OPS_STATUS_LABELS["unknown"])
    parts = [
        _count_part("内容回写失败", counts.get("content_change_failures", 0)),
        _count_part("Webhook 失败", counts.get("webhook_failures", 0)),
        _count_part("处理中", counts.get("webhook_processing", 0)),
        _count_part("慢请求", counts.get("slow_webhooks", 0)),
    ]
    return f"{status_label}：{_join_non_empty(parts)}。{_ops_attention_hint(counts)}"


def webhook_line(item: dict[str, Any]) -> str:
    return (
        f"{item.get('eventType', '')}｜{item.get('businessKey', '')}｜"
        f"{item.get('errorType', '')}｜{item.get('errorMessagePreview', '')}"
    )


def offline_review_line(summary: Any) -> str:
    if not bool(getattr(summary, "ran", False)):
        return f"{offline_review_skipped_reason_text(summary)}。"
    return (
        "最近一轮离线复盘已执行："
        f"质检 {int(getattr(summary, 'review_count', 0) or 0)}，"
        f"知识缺口 {int(getattr(summary, 'gap_count', 0) or 0)}，"
        f"客户记忆 {int(getattr(summary, 'profile_count', 0) or 0)}。"
    )


def offline_review_next_action(summary: Any) -> str:
    if not bool(getattr(summary, "ran", False)):
        return OFFLINE_REVIEW_SKIPPED_NEXT_ACTION
    return OFFLINE_REVIEW_COMPLETED_NEXT_ACTION


def offline_review_skipped_reason_text(summary: Any) -> str:
    reason = str(getattr(summary, "skipped_reason", "") or "not_run")
    return OFFLINE_REVIEW_SKIPPED_REASON_LABELS.get(
        reason,
        OFFLINE_REVIEW_SKIPPED_FALLBACK,
    )


def _count_part(label: str, value: Any) -> str:
    count = int(value or 0)
    return f"{label} {count} 条" if count else ""


def _join_non_empty(parts: list[str]) -> str:
    values = [part for part in parts if part]
    return "，".join(values) if values else "暂无失败或积压"


def _ops_attention_hint(counts: dict[str, Any]) -> str:
    if int(counts.get("webhook_failures", 0) or 0):
        return "先看 Webhook 失败记录，再核对内容回写历史。"
    if int(counts.get("content_change_failures", 0) or 0):
        return "先看内容回写历史，确认是否有商品或知识同步失败。"
    if int(counts.get("slow_webhooks", 0) or 0):
        return "先看慢请求记录，确认是否有外部接口超时。"
    if int(counts.get("webhook_processing", 0) or 0):
        return "有消息仍在处理，稍后再复查是否堆积。"
    return "无需立刻处理。"


def mask_address(address: str) -> str:
    compact_value = "".join(address.split())
    if not compact_value:
        return ""
    if len(compact_value) <= ADDRESS_PREVIEW_LENGTH:
        return compact_value[:1] + "***"
    return compact_value[:ADDRESS_PREVIEW_LENGTH] + "..."


def mask_identifier(value: str) -> str:
    compact_value = value.strip()
    if not compact_value:
        return ""
    if len(compact_value) <= IDENTIFIER_PREFIX_LENGTH + IDENTIFIER_SUFFIX_LENGTH:
        return "***"
    return (
        compact_value[:IDENTIFIER_PREFIX_LENGTH]
        + "..."
        + compact_value[-IDENTIFIER_SUFFIX_LENGTH:]
    )


def short_identifier(value: str) -> str:
    compact_value = value.strip()
    if not compact_value:
        return "***"
    return compact_value[-TRANSFER_ID_SUFFIX_LENGTH:]


def redact_sensitive_text(content: str) -> str:
    clean_content, _tags = parse_ump_tags(content)
    clean_content = DANGLING_UMP_PATTERN.sub("", clean_content)

    def replace_phone(match: re.Match[str]) -> str:
        return mask_phone(match.group(0))

    def replace_address(match: re.Match[str]) -> str:
        return mask_address(match.group(0))

    phone_redacted = PHONE_PATTERN.sub(replace_phone, clean_content)
    return snippet(ADDRESS_PATTERN.sub(replace_address, phone_redacted))


def _safe_lookup_query_preview(query: str) -> str:
    clean_query = query.strip()
    if not clean_query:
        return ""

    def replace_phone(match: re.Match[str]) -> str:
        return mask_phone(match.group(0))

    def replace_address(match: re.Match[str]) -> str:
        return mask_address(match.group(0))

    phone_redacted = PHONE_PATTERN.sub(replace_phone, clean_query)
    return snippet(ADDRESS_PATTERN.sub(replace_address, phone_redacted))
