"""企微客服外发投递合同，与队列消费机制分离。

投递状态机：pending（待发送）→ sending（发送中）→ sent（已发送成功）
→ unknown（结果未知，需人工确认）→ pending（人工重试后）
→ failed（明确失败，需人工重试）→ pending（人工重试后）。

规则：
- 每个外发分段使用稳定业务幂等键，并作为供应商 msgid 传递。
- 同一幂等键只有首个占位者可发送，重复消费直接返回当前状态。
- 认领签发唯一凭证，终态写入必须 fencing，旧凭证迟到提交直接拒绝。
- 发送租约过期未终态视为持有者崩溃，新认领可接管，旧凭证失效。
- 传输异常（超时、连接中断、响应丢失）一律记 unknown，不自动重发。
- 供应商明确拒绝记 failed，不自动重发，由人工确认后重试。
- 发送中且租约有效时重复消费直接退避，不触碰持有者的行。
"""

from app.database import db_session_scope
from app.logger import setup_logger
from app.repository.wecom_kf_outbound_repo import (
    STATUS_FAILED,
    STATUS_SENDING,
    STATUS_SENT,
    STATUS_UNKNOWN,
    WecomKfOutboundRepo,
)

logger = setup_logger()

OUTBOUND_KEY_PREFIX = "wecom_kf:out"


def build_outbound_key(inbound_msg_id: str, part: str = "text") -> str:
    """由入站消息标识与分段名生成稳定幂等键。"""
    return f"{OUTBOUND_KEY_PREFIX}:{inbound_msg_id}:{part}"


def build_content_hash(msgtype: str, content: str) -> str:
    """由消息类型与规范内容生成内容哈希，同键异内容必须冲突。"""
    import hashlib

    return hashlib.sha256(f"{msgtype}|{content}".encode("utf-8")).hexdigest()


async def send_text_guarded(
    client,
    external_userid: str,
    inbound_msg_id: str,
    content: str,
    part: str = "text",
    open_kfid: str = "",
) -> str:
    """幂等发送文本，返回终态，未知与失败不自动重发。"""
    outbound_key = build_outbound_key(inbound_msg_id, part)
    content_hash = build_content_hash("text", content)
    async with db_session_scope():
        row, can_send = await WecomKfOutboundRepo().claim_for_send(
            outbound_key,
            open_kfid,
            external_userid,
            inbound_msg_id,
            "text",
            content_hash,
        )
    if not can_send:
        return await _handle_duplicate_claim(outbound_key, dict(row))
    claim_token = str(row.get("claim_token", "") or "")
    try:
        result = await client.send_kf_text(external_userid, content, msgid=outbound_key)
    except Exception as exc:
        logger.error("客服文本发送传输异常 user=%s err=%s", external_userid, exc)
        async with db_session_scope():
            await WecomKfOutboundRepo().mark_unknown(
                outbound_key,
                claim_token,
                f"传输异常:{type(exc).__name__}:{exc}",
            )
        return STATUS_UNKNOWN
    async with db_session_scope():
        repo = WecomKfOutboundRepo()
        if result.get("errcode") == 0:
            if await repo.mark_sent(outbound_key, claim_token):
                return STATUS_SENT
            logger.warning("客服文本发送凭证过期 key=%s，转人工确认", outbound_key)
            return STATUS_UNKNOWN
        await repo.mark_failed(outbound_key, claim_token, str(result.get("errmsg")))
        logger.error(
            "客服文本回复发送失败 user=%s err=%s",
            external_userid,
            result.get("errmsg"),
        )
        return STATUS_FAILED


async def send_link_guarded(
    client,
    external_userid: str,
    inbound_msg_id: str,
    title: str,
    url: str,
    desc: str = "",
    thumb_media_id: str = "",
    part: str = "card",
    open_kfid: str = "",
) -> str:
    """幂等发送图文链接，返回终态，未知与失败不自动重发。"""
    outbound_key = build_outbound_key(inbound_msg_id, part)
    content_hash = build_content_hash(
        "link", "|".join([title, url, desc, thumb_media_id])
    )
    async with db_session_scope():
        row, can_send = await WecomKfOutboundRepo().claim_for_send(
            outbound_key,
            open_kfid,
            external_userid,
            inbound_msg_id,
            "link",
            content_hash,
        )
    if not can_send:
        return await _handle_duplicate_claim(outbound_key, dict(row))
    claim_token = str(row.get("claim_token", "") or "")
    try:
        result = await client.send_kf_link(
            external_userid=external_userid,
            title=title,
            url=url,
            desc=desc,
            thumb_media_id=thumb_media_id,
            msgid=outbound_key,
        )
    except Exception as exc:
        logger.error("客服卡片发送传输异常 user=%s err=%s", external_userid, exc)
        async with db_session_scope():
            await WecomKfOutboundRepo().mark_unknown(
                outbound_key,
                claim_token,
                f"传输异常:{type(exc).__name__}:{exc}",
            )
        return STATUS_UNKNOWN
    async with db_session_scope():
        repo = WecomKfOutboundRepo()
        if result.get("errcode") == 0:
            if await repo.mark_sent(outbound_key, claim_token):
                return STATUS_SENT
            logger.warning("客服卡片发送凭证过期 key=%s，转人工确认", outbound_key)
            return STATUS_UNKNOWN
        await repo.mark_failed(outbound_key, claim_token, str(result.get("errmsg")))
        logger.error(
            "客服卡片发送失败 user=%s err=%s",
            external_userid,
            result.get("errmsg"),
        )
        return STATUS_FAILED


async def send_event_guarded(
    client,
    event_code: str,
    inbound_msg_id: str,
    content: str,
    part: str = "welcome",
    open_kfid: str = "",
) -> str:
    """幂等发送欢迎语/事件响应，统一经过投递账本，返回终态。

    事件响应同样走 pending→sending→sent/unknown/failed 状态机，
    未知与失败不自动重发，由人工确认后重排。
    """
    outbound_key = build_outbound_key(inbound_msg_id, part)
    content_hash = build_content_hash("event", f"{event_code}|{content}")
    async with db_session_scope():
        row, can_send = await WecomKfOutboundRepo().claim_for_send(
            outbound_key,
            open_kfid,
            "",
            inbound_msg_id,
            "event",
            content_hash,
        )
    if not can_send:
        return await _handle_duplicate_claim(outbound_key, dict(row))
    claim_token = str(row.get("claim_token", "") or "")
    try:
        result = await client.send_kf_event_text(
            event_code, content, msgid=outbound_key
        )
    except Exception as exc:
        logger.error("客服事件响应传输异常 code=%s err=%s", event_code, exc)
        async with db_session_scope():
            await WecomKfOutboundRepo().mark_unknown(
                outbound_key,
                claim_token,
                f"传输异常:{type(exc).__name__}:{exc}",
            )
        return STATUS_UNKNOWN
    async with db_session_scope():
        repo = WecomKfOutboundRepo()
        if result.get("errcode") == 0:
            if await repo.mark_sent(outbound_key, claim_token):
                return STATUS_SENT
            logger.warning("客服事件响应凭证过期 key=%s，转人工确认", outbound_key)
            return STATUS_UNKNOWN
        await repo.mark_failed(outbound_key, claim_token, str(result.get("errmsg")))
        logger.error(
            "客服事件响应发送失败 code=%s err=%s",
            event_code,
            result.get("errmsg"),
        )
        return STATUS_FAILED


async def request_manual_retry(outbound_key: str, operator: str, reason: str) -> bool:
    """人工确认后重新排队，仅未知或失败状态可转回待发送。"""
    async with db_session_scope():
        return await WecomKfOutboundRepo().requeue_for_manual_retry(
            outbound_key, operator, reason
        )


async def _handle_duplicate_claim(outbound_key: str, row: dict) -> str:
    """重复消费保护：终态直接返回，发送中且租约有效则退避。

    绝不触碰持有者的行：持有者凭凭证正常终态；持有者崩溃后由过期接管
    恢复，不在此盲目转未知覆盖。
    """
    status = str(row.get("status", ""))
    if status == STATUS_SENT:
        return STATUS_SENT
    if status == STATUS_SENDING:
        logger.warning("外发发送中被重复消费 key=%s，退避等待持有者终态", outbound_key)
        return STATUS_SENDING
    return status or STATUS_UNKNOWN
