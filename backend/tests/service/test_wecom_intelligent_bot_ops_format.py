from app.service.wecom.intelligent_bot_ops_format import (
    compact_transfer,
    offline_review_line,
    offline_review_next_action,
    ops_summary_line,
    transfer_line,
)


class _Transfer:
    id = "da8f723e-d755-4868-8c48-bf9813a77f40"
    session_id = "sess_001"
    user_id = "user_001"
    reason = "客户要求人工确认配送"
    conversation_summary = "客户 13812345678 问配送到隐私路 99 号的时间。"
    created_at = "2026-07-04 09:00:00"


class _TransferWithUmp:
    id = "da8f723e-d755-4868-8c48-bf9813a77f41"
    session_id = "sess_002"
    user_id = "user_002"
    reason = "转人工"
    conversation_summary = (
        "AI：好的，给您～ "
        "[UMP: type=card&id=3437083272&title=%E5%B0%8F%E7%86%8A%E8%9B%8B%E7%B3%95]"
    )
    created_at = "2026-07-04 09:05:00"


class _TransferWithDanglingUmp:
    id = "da8f723e-d755-4868-8c48-bf9813a77f42"
    session_id = "sess_003"
    user_id = "user_003"
    reason = "转人工"
    conversation_summary = (
        "AI：好的，给您～ [UMP: type=card&id=3437083272&title=%E5%B0%8F"
    )
    created_at = "2026-07-04 09:06:00"


class _SkippedOfflineReviewSummary:
    ran = False
    skipped_reason = "outside_night_window"


class _UnknownSkippedOfflineReviewSummary:
    ran = False
    skipped_reason = "scheduler_paused"


def test_ops_summary_line_uses_staff_readable_status() -> None:
    reply = ops_summary_line(
        {
            "status": "attention",
            "counts": {
                "content_change_failures": 1,
                "webhook_failures": 2,
                "webhook_processing": 0,
                "slow_webhooks": 1,
            },
        }
    )

    assert "系统需要关注" in reply
    assert "Webhook 失败 2 条" in reply
    assert "先看 Webhook 失败记录" in reply
    assert "attention" not in reply


def test_transfer_line_includes_safe_summary_preview() -> None:
    item = compact_transfer(_Transfer())
    reply = transfer_line(item)

    assert "工单尾号 77f40" in reply
    assert "客户要求人工确认配送" in reply
    assert "摘要：" in reply
    assert "13812345678" not in reply
    assert "隐私路 99 号" not in reply
    assert "user_001" not in reply


def test_transfer_line_removes_ump_card_marker_from_summary() -> None:
    item = compact_transfer(_TransferWithUmp())
    reply = transfer_line(item)

    assert "工单尾号 77f41" in reply
    assert "AI：好的，给您～" in reply
    assert "UMP" not in reply
    assert "type=card" not in reply
    assert "%E5%B0%8F" not in reply


def test_offline_review_line_hides_raw_skipped_reason() -> None:
    reply = offline_review_line(_SkippedOfflineReviewSummary())
    next_action = offline_review_next_action(_SkippedOfflineReviewSummary())

    assert "当前不在夜间复盘窗口" in reply
    assert "如需立即复盘" in next_action
    assert "outside_night_window" not in reply
    assert "skippedReason" not in next_action


def test_offline_review_line_hides_unknown_raw_skipped_reason() -> None:
    reply = offline_review_line(_UnknownSkippedOfflineReviewSummary())

    assert "原因需到后台调度日志确认" in reply
    assert "scheduler_paused" not in reply


def test_transfer_line_removes_dangling_ump_card_marker() -> None:
    item = compact_transfer(_TransferWithDanglingUmp())
    reply = transfer_line(item)

    assert "工单尾号 77f42" in reply
    assert "AI：好的，给您～" in reply
    assert "UMP" not in reply
    assert "type=card" not in reply
    assert "%E5%B0%8F" not in reply
