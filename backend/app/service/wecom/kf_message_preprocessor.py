"""微信客服非文本消息预处理。"""

import base64
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.logger import setup_logger
from app.service.llm.client import asr_transcribe
from app.utils import convert_amr_to_wav

if TYPE_CHECKING:
    from app.service.wecom.kf_message_queue import KfIncomingMessage

logger = setup_logger()


@dataclass(frozen=True)
class PreparedKfMessage:
    """可交给 ChatService 的消息内容。"""

    content: str
    image_base64: str = ""


async def preprocess_kf_message(
    client, msg: "KfIncomingMessage"
) -> PreparedKfMessage | None:
    """预处理文本、图片和语音；无法处理时发送非文本兜底并返回 None。"""
    if msg.msgtype == "text":
        return PreparedKfMessage(content=msg.content)

    if msg.msgtype == "image" and msg.media_id:
        image_base64 = await _download_image(client, msg)
        if image_base64:
            return PreparedKfMessage(
                content="[用户发送了一张图片]",
                image_base64=image_base64,
            )
    elif msg.msgtype == "voice" and msg.media_id:
        asr_text = await _transcribe_voice(client, msg)
        if asr_text:
            return PreparedKfMessage(content=f"[语音] {asr_text}")

    fallback_map = {
        "video": "抱歉，我暂时无法查看视频，麻烦您用文字描述一下需要咨询的问题~",
        "file": "抱歉，我暂时无法接收文件，请直接用文字告诉我您的问题，我会尽快为您解答 :)",
        "location": "我看到您发了一个位置信息~ 请问是想了解配送范围还是门店地址呢？",
    }
    fallback = fallback_map.get(
        msg.msgtype,
        "您好~ 我暂时只能识别文字和图片消息，麻烦用文字描述一下哦 :)",
    )
    logger.info(
        "非文本消息返回兜底提示 type=%s user=%s", msg.msgtype, msg.external_userid
    )
    result = await client.send_kf_text(msg.external_userid, fallback)
    if result.get("errcode") != 0:
        logger.error(
            "兜底提示发送失败 user=%s err=%s",
            msg.external_userid,
            result.get("errmsg"),
        )
    return None


async def _download_image(client, msg: "KfIncomingMessage") -> str:
    try:
        media_bytes = await client.download_kf_temp_media(msg.media_id)
        if not media_bytes:
            return ""
        logger.info(
            "图片素材已下载 size=%dB user=%s",
            len(media_bytes),
            msg.external_userid,
        )
        return base64.b64encode(media_bytes).decode("utf-8")
    except Exception as exc:
        logger.error("下载图片素材异常 user=%s err=%s", msg.external_userid, exc)
        return ""


async def _transcribe_voice(client, msg: "KfIncomingMessage") -> str:
    try:
        voice_bytes = await client.download_kf_temp_media(msg.media_id)
        if not voice_bytes:
            return ""
        try:
            wav_bytes = await convert_amr_to_wav(voice_bytes)
        except Exception as exc:
            logger.error("语音转码失败 user=%s err=%s", msg.external_userid, exc)
            return ""
        if not wav_bytes:
            return ""
        raw_asr_text = await asr_transcribe(
            audio_base64=base64.b64encode(wav_bytes).decode("utf-8"),
            mime_type="audio/wav",
            language="zh",
        )
        asr_text = raw_asr_text.strip()
        if asr_text:
            logger.info(
                "ASR 语音转文字成功 原文=%s user=%s",
                asr_text[:50],
                msg.external_userid,
            )
        return asr_text
    except Exception as exc:
        logger.error("语音 ASR 转写异常 user=%s err=%s", msg.external_userid, exc)
        return ""
