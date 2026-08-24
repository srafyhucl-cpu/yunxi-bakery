"""企微回调入口（统一：自建应用 + 微信客服）。

客户发消息给员工（自建应用）、或微信用户发消息给客服（微信客服），都推送到此接口。
需要先在企微后台配置回调 URL，并开启「微信客服消息和事件」开关。

流程：
1. GET 请求验证 URL（echostr 解密）
2. POST 接收消息/事件通知（解密 XML → 根据类型分发处理）

消息类型分流：
- MsgType=text  → 自建应用消息 → 入队 wecom_queue
- MsgType=event + Event=kf_msg_or_event → 微信客服通知 → sync_msg拉取 → 入队 kf_queue

异步设计：
- 回调接口只负责解密 + 入队（<1ms），满足企微 5s 超时要求
- 实际 AI 对话 + 发回复由各队列的 Worker 执行
"""

import time
import xml.etree.ElementTree as ET

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from app.config import settings
from app.logger import setup_logger
from app.service.wecom.crypto import decrypt, verify_signature

logger = setup_logger()

router = APIRouter(prefix="/api/v1/wecom", tags=["wecom"])


def _parse_message_xml(xml_str: str) -> dict:
    """解析企微回调消息 XML 为字典。"""
    root = ET.fromstring(xml_str)
    result: dict = {}
    for child in root:
        result[child.tag] = child.text or ""
    return result


@router.get("/callback")
async def verify_url(
    msg_signature: str,
    timestamp: str,
    nonce: str,
    echostr: str,
) -> PlainTextResponse:
    """验证回调 URL（企微 GET 请求）。自建应用与微信共用此验证。"""
    if not settings.WECOM_ENCODING_AES_KEY or not settings.WECOM_TOKEN:
        logger.error("WECOM_ENCODING_AES_KEY 或 WECOM_TOKEN 未配置")
        return PlainTextResponse("配置未就绪", status_code=503)

    if not verify_signature(
        settings.WECOM_TOKEN, timestamp, nonce, echostr, msg_signature
    ):
        logger.warning("URL 验证签名失败")
        return PlainTextResponse("签名验证失败", status_code=403)

    try:
        plain = decrypt(settings.WECOM_ENCODING_AES_KEY, echostr)
        return PlainTextResponse(plain)
    except Exception as exc:
        logger.error("echostr 解密失败: %s", exc)
        return PlainTextResponse("解密失败", status_code=500)


async def _handle_kf_callback(msg: dict) -> None:
    """处理微信客服回调通知。"""
    from app.service.wecom.client import get_wecom_client
    from app.service.wecom.kf_callback_processor import KfCallbackProcessor

    await KfCallbackProcessor(get_wecom_client()).handle_callback(msg)


@router.post("/callback")
async def receive_message(request: Request) -> PlainTextResponse:
    """接收企微推送的消息和事件（POST）。根据类型分流处理。"""
    if not settings.WECOM_ENCODING_AES_KEY or not settings.WECOM_TOKEN:
        return PlainTextResponse("配置未就绪", status_code=503)

    raw = await request.body()
    xml_str = raw.decode("utf-8")

    # 签名参数从 URL query string 获取（非 XML body）
    msg_signature = request.query_params.get("msg_signature", "")
    timestamp = request.query_params.get("timestamp", str(int(time.time())))
    nonce = request.query_params.get("nonce", "")

    # 加密消息体从 XML body 提取
    try:
        root = ET.fromstring(xml_str)
        encrypt_xml = root.findtext("Encrypt") or ""
    except ET.ParseError as exc:
        logger.error("XML 解析失败: %s", exc)
        return PlainTextResponse("XML 解析失败", status_code=400)

    # 验签
    if not verify_signature(
        settings.WECOM_TOKEN, timestamp, nonce, encrypt_xml, msg_signature
    ):
        logger.warning("消息签名验证失败")
        return PlainTextResponse("签名验证失败", status_code=403)

    # 解密
    try:
        plain_xml = decrypt(settings.WECOM_ENCODING_AES_KEY, encrypt_xml)
    except Exception as exc:
        logger.error("消息解密失败: %s", exc)
        return PlainTextResponse("解密失败", status_code=500)

    msg = _parse_message_xml(plain_xml)
    msg_type = msg.get("MsgType", "")

    # ── 分流：微信客服事件 ──
    if msg_type == "event":
        event_type = msg.get("Event", "")
        if event_type == "kf_msg_or_event":
            await _handle_kf_callback(msg)
        else:
            logger.info("收到其他企微事件 type=%s（未处理）", event_type)
        return PlainTextResponse("")

    # ── 自建应用消息（原有逻辑）──
    content = msg.get("Content", "")
    from_user = msg.get("FromUserName", "")
    msg_id = msg.get("MsgId", "")

    logger.info(
        "收到企微消息 type=%s from=%s msg_id=%s",
        msg_type,
        from_user,
        msg_id,
    )

    # 空文本消息直接忽略
    if msg_type == "text" and not content.strip():
        return PlainTextResponse("")

    # 非文本消息（图片/语音/视频等）：显式记录，便于排查与后续扩展
    if msg_type != "text":
        logger.info(
            "企微非文本消息暂不支持，已跳过处理 type=%s from=%s msg_id=%s",
            msg_type,
            from_user,
            msg_id,
        )
        return PlainTextResponse("")

    # 异步入队：立即返回，后台 Worker 负责处理
    from app.service.wecom.message_queue import wecom_queue, WeComIncomingMessage

    success = await wecom_queue.enqueue(
        WeComIncomingMessage(
            external_user_id=from_user,
            content=content,
            channel_msg_id=msg_id,
        )
    )
    if not success:
        logger.warning("企微消息队列已满，丢弃消息 user=%s", from_user)

    # 企微回调要求立即返回 200，内容为空
    return PlainTextResponse("")
