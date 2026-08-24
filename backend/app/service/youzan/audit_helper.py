"""有赞 Webhook 审计状态标记公共工具。

消除 event_item / event_trade 中逻辑完全相同、仅 business_type 不同的
_mark_item_audit / _mark_trade_audit 重复函数。
"""

from app.models.youzan_webhook_event import (
    YouzanWebhookEventUpdate,
    YouzanWebhookStatus,
)
from app.repository.youzan_webhook_event_repo import YouzanWebhookEventRepo


async def mark_audit(
    audit_repo: YouzanWebhookEventRepo | None,
    audit_id: int | None,
    status: str,
    process_stage: str,
    business_type: str,
    error_type: str = "",
    error_message: str = "",
    business_key: str = "",
) -> None:
    """统一更新 Webhook 事件审计状态。

    参数：
        audit_repo: 审计仓库实例，为 None 时静默跳过
        audit_id: 审计记录 ID，为 None 时静默跳过
        status: 目标状态（PROCESSING / PROCESSED / FAILED / SKIPPED）
        process_stage: 处理阶段标识字符串
        business_type: 业务类型（ITEM / TRADE 等）
        error_type: 错误类型标识，仅 FAILED 时填写
        error_message: 错误详细信息，仅 FAILED 时填写
        business_key: 业务主键（商品 ID / 订单号）
    """
    if audit_repo is None or audit_id is None:
        return
    if status == YouzanWebhookStatus.PROCESSING:
        await audit_repo.mark_processing(
            audit_id,
            process_stage,
            business_type=business_type,
            business_key=business_key,
        )
        return
    await audit_repo.mark_result(
        audit_id,
        YouzanWebhookEventUpdate(
            status=status,
            process_stage=process_stage,
            business_type=business_type,
            business_key=business_key,
            error_type=error_type,
            error_message=error_message,
        ),
    )
