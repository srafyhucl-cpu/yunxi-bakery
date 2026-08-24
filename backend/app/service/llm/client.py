"""
MiMo / DeepSeek API 调用层。

仅封装 OpenAI SDK 的 MiMo ASR 窄适配。
文本模型调用统一由 LangChain model registry 提供。

所有 LLM 调用异常统一抛出 LLMError，由上层处理降级兜底。
"""

import httpx
from openai import AsyncOpenAI

from app.config import settings
from app.exceptions import LLMError
from app.logger import setup_logger

logger = setup_logger()

# 全局单例客户端
_mimo_client: AsyncOpenAI | None = None


def get_mimo_client() -> AsyncOpenAI:
    """获取或初始化 MiMo 异步客户端（单例模式）。"""
    global _mimo_client
    if _mimo_client is None:
        # trust_env=False 禁止读取系统代理环境变量
        # MiMo 使用 api-key 认证头（非标准 Bearer），通过 default_headers 传入
        _mimo_client = AsyncOpenAI(
            api_key=settings.MIMO_API_KEY,
            base_url=settings.MIMO_BASE_URL,
            timeout=settings.MIMO_TIMEOUT_SECONDS,
            http_client=httpx.AsyncClient(trust_env=False),
            default_headers={"api-key": settings.MIMO_API_KEY},
        )
    return _mimo_client


async def asr_transcribe(
    audio_base64: str,
    mime_type: str = "audio/wav",
    language: str = "zh",
) -> str:
    """
    调用 MiMo ASR 模型将语音转为文字。

    参数：
        audio_base64: 音频的 base64 编码字符串（不含 data URI 前缀）
        mime_type: 音频 MIME 类型（audio/wav 或 audio/mpeg）
        language: 语种代码（zh/en/auto）
    返回：
        识别出的文字内容
    异常：
        LLMError: ASR 调用失败时抛出
    """
    client = get_mimo_client()
    audio_data_url = f"data:{mime_type};base64,{audio_base64}"

    try:
        response = await client.chat.completions.create(
            model=settings.MIMO_ASR_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_audio",
                            "input_audio": {"data": audio_data_url},
                        }
                    ],
                }
            ],
            extra_body={
                "asr_options": {"language": language},
            },
            max_tokens=1024,
            temperature=0,
        )
        text = response.choices[0].message.content or ""
        logger.info("ASR 识别完成 长度=%d 语言=%s", len(text), language)
        return text
    except Exception as exc:
        logger.error("MiMo ASR 调用失败: %s", exc)
        raise LLMError("MiMo ASR 调用失败") from exc
