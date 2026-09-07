"""微信支付通知 intake：明确状态机与原子认领，杜绝永久跳过。

状态机：received（已归档待认领）→ processing（认领持有租约）
→ processed（业务完成终态）；失败进入 failed（可重试，相当于
retryable_failed），超过最大次数进入 dead_letter（需人工处理）。

认领合同 claim_notify(event_id, lease_seconds)：
- 只有 processed 才直接确认重复成功（decision=duplicate）。
- received、到期 processing、failed 必须可以重新认领（claimed）。
- 租约有效期内的 processing 返回 processing（忙），调用方稍后重试，
  不得当作已处理成功。
- dead_letter 不自动认领，返回 dead，需人工处理。
- 使用 attempt_count 作 claim token：完成与失败标记必须校验 token，
  陈旧 worker 的提交直接拒绝。

归档、业务消费、完成标记必须在调用方同一事务提交；业务异常让事务
回滚（不留半完成 intake），或显式标记 failed 等待重投。
"""

import json

from app.repository.inbox_repo import InboxRepo

NOTIFY_QUEUE = "wechat_pay_notify"
DEFAULT_NOTIFY_LEASE_SECONDS = 300

DECISION_CLAIMED = "claimed"
DECISION_DUPLICATE = "duplicate"
DECISION_PROCESSING = "processing"
DECISION_DEAD = "dead"


def build_notify_key(event_id: str) -> str:
    """由微信事件标识生成 intake 幂等键。"""
    return f"{NOTIFY_QUEUE}:{event_id}"


def extract_notify_identity(payload: dict) -> tuple[str, str]:
    """提取事件标识与事件类型，缺失直接拒绝。"""
    event_id = str(payload.get("id", "") or "").strip()
    event_type = str(payload.get("event_type", "") or "").strip()
    if not event_id:
        raise ValueError("微信支付通知缺少事件标识")
    return event_id, event_type


def _lease_modifier(lease_seconds: int) -> str:
    """生成 SQLite datetime 修饰符，兼容正负租约。"""
    sign = "+" if int(lease_seconds) >= 0 else "-"
    return f"{sign}{abs(int(lease_seconds))} seconds"


async def claim_notify(
    db,
    event_id: str,
    payload: dict | None = None,
    *,
    lease_seconds: int = DEFAULT_NOTIFY_LEASE_SECONDS,
) -> dict:
    """原子认领通知事件，返回决策与认领凭证。

    返回 {"decision", "claim_token", "attempt_count}：
    - claimed：本次获得处理权，claim_token=attempt_count，调用方必须在
      业务完成后用同一 token 提交 complete/fail。
    - duplicate：已是 processed 终态，调用方可直接确认重复成功。
    - processing：已有 worker 持有有效租约，调用方不得重复处理。
    - dead：已进入 dead_letter，需人工处理，不自动认领。
    """
    return await claim_notify_key(
        db, build_notify_key(event_id), payload, lease_seconds=lease_seconds
    )


async def claim_notify_key(
    db,
    message_key: str,
    payload: dict | None = None,
    *,
    lease_seconds: int = DEFAULT_NOTIFY_LEASE_SECONDS,
) -> dict:
    """按完整幂等键原子认领，与 claim_notify 同合同。"""
    repo = InboxRepo(db)
    await repo.enqueue(
        NOTIFY_QUEUE, message_key, json.dumps(payload or {}, ensure_ascii=False)
    )
    cursor = await db.execute(
        "UPDATE inbox_events SET status = 'processing', "
        "attempt_count = attempt_count + 1, "
        "lease_until = datetime('now', ?), updated_at = datetime('now') "
        "WHERE message_key = ? AND (status = 'received' "
        "OR (status = 'failed' AND next_attempt_at <= datetime('now')) "
        "OR (status = 'processing' AND (lease_until IS NULL "
        "OR lease_until <= datetime('now'))))",
        (_lease_modifier(lease_seconds), message_key),
    )
    if int(cursor.rowcount or 0) == 1:
        rows = await db.execute_fetchall(
            "SELECT attempt_count FROM inbox_events WHERE message_key = ?",
            (message_key,),
        )
        attempt = int(rows[0]["attempt_count"]) if rows else 0
        return {
            "decision": DECISION_CLAIMED,
            "claim_token": attempt,
            "attempt_count": attempt,
        }
    rows = await db.execute_fetchall(
        "SELECT status, attempt_count FROM inbox_events WHERE message_key = ?",
        (message_key,),
    )
    status = str(rows[0]["status"]) if rows else ""
    attempt = int(rows[0]["attempt_count"]) if rows else 0
    if status == "processed":
        return {
            "decision": DECISION_DUPLICATE,
            "claim_token": None,
            "attempt_count": attempt,
        }
    if status == "dead_letter":
        return {
            "decision": DECISION_DEAD,
            "claim_token": None,
            "attempt_count": attempt,
        }
    return {
        "decision": DECISION_PROCESSING,
        "claim_token": None,
        "attempt_count": attempt,
    }


async def complete_notify_key(
    db, message_key: str, claim_token: int | None = None
) -> None:
    """按完整幂等键标记消费完成，与 claim_notify_key 配对。

    传 token 时校验认领归属与租约有效性，陈旧 worker 直接拒绝；
    不传 token 时保持旧盲标记语义（兼容存量调用）。
    """
    if claim_token is None:
        await InboxRepo(db).mark_processed(message_key)
        return
    cursor = await db.execute(
        "UPDATE inbox_events SET status = 'processed', lease_until = NULL, "
        "updated_at = datetime('now') WHERE message_key = ? "
        "AND status = 'processing' AND attempt_count = ? "
        "AND lease_until IS NOT NULL AND lease_until > datetime('now')",
        (message_key, int(claim_token)),
    )
    if int(cursor.rowcount or 0) != 1:
        raise ValueError(f"微信支付通知认领已过期 key={message_key}，需重新认领")


async def complete_notify(db, event_id: str, claim_token: int | None = None) -> None:
    """标记通知消费完成，调用方事务统一提交。

    传 token 时校验认领归属与租约有效性，陈旧 worker 直接拒绝；
    不传 token 时保持旧盲标记语义（兼容存量调用）。
    """
    await complete_notify_key(db, build_notify_key(event_id), claim_token)


async def fail_notify(
    db,
    event_id: str,
    claim_token: int,
    error: str,
    *,
    retryable: bool = True,
) -> None:
    """标记通知处理失败，调用方事务统一提交。

    与 complete_notify 一致校验 claim token 与租约有效性：租约过期后
    陈旧 worker 的失败标记同样被拒绝，防止覆盖新持有者状态。
    retryable 进入 failed 等待重投，非 retryable 直接进入 dead_letter。
    """
    message_key = build_notify_key(event_id)
    cursor = await db.execute(
        "UPDATE inbox_events SET status = ?, lease_until = NULL, "
        "next_attempt_at = datetime('now', '+15 seconds'), last_error = ?, "
        "updated_at = datetime('now') WHERE message_key = ? "
        "AND status = 'processing' AND attempt_count = ? "
        "AND lease_until IS NOT NULL AND lease_until > datetime('now')",
        (
            "failed" if retryable else "dead_letter",
            str(error or "")[:500],
            message_key,
            int(claim_token),
        ),
    )
    if int(cursor.rowcount or 0) != 1:
        raise ValueError(f"微信支付通知认领已过期 event={event_id}，需重新认领")


async def archive_notify(db, event_id: str, payload: dict) -> bool:
    """归档通知载荷，返回是否首次归档，调用方事务统一提交。

    旧入口保留供查询恢复等幂等占位使用；支付/退款主通知链路须改用
    claim_notify 明确状态机，不得把“键已存在”直接当作已处理。
    """
    return await InboxRepo(db).enqueue(
        NOTIFY_QUEUE,
        build_notify_key(event_id),
        json.dumps(payload, ensure_ascii=False),
    )
