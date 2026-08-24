"""项目公共工具函数。"""

import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo


def yuan_to_fen(amount: object) -> int:
    """把金额（元）安全换算为分，避免浮点精度误差；非法值返回 0。"""
    try:
        return int(Decimal(str(amount)) * 100)
    except (InvalidOperation, TypeError, ValueError):
        return 0


BEIJING_TIMEZONE = ZoneInfo("Asia/Shanghai")


def now_beijing() -> datetime.datetime:
    """返回北京时间。"""
    return datetime.datetime.now(BEIJING_TIMEZONE)


def now_beijing_naive() -> datetime.datetime:
    """返回不带时区信息的北京时间，兼容旧数据库时间字符串。"""
    return now_beijing().replace(tzinfo=None)


def now_str() -> str:
    """返回当前时间的格式化字符串（%Y-%m-%d %H:%M:%S）。"""
    return now_beijing().strftime("%Y-%m-%d %H:%M:%S")


async def convert_amr_to_wav(amr_bytes: bytes) -> bytes:
    """使用系统 ffmpeg 将 AMR 格式字节流转换为 WAV 格式。"""
    import asyncio
    import logging

    logger = logging.getLogger("yunxi_bot")

    process = await asyncio.create_subprocess_exec(
        "ffmpeg",
        "-i",
        "pipe:0",  # 从 stdin 读取
        "-f",
        "wav",  # 输出格式为 wav
        "-acodec",
        "pcm_s16le",  # PCM 编码
        "-ar",
        "16000",  # 16kHz 采样率
        "-ac",
        "1",  # 单声道
        "-y",  # 覆盖输出
        "pipe:1",  # 输出到 stdout
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await process.communicate(input=amr_bytes)
    except Exception as e:
        logger.error("ffmpeg 运行异常: %s", e)
        raise

    if process.returncode != 0:
        err_msg = stderr.decode("utf-8", errors="ignore") if stderr else "unknown"
        logger.error("ffmpeg 音频转码失败: %s", err_msg)
        raise RuntimeError(f"ffmpeg conversion failed: {err_msg}")
    return stdout
