"""项目公共工具函数。"""

import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from zoneinfo import ZoneInfo


def yuan_to_fen(amount: object) -> int:
    """把金额（元）换算为分，全仓唯一的元→分合同。

    使用十进制半向上舍入，非法输入直接抛出，不静默归零。
    负数、NaN、Infinity 一律拒绝：结算域金额非负， Exception 信息保留
    “金额”前缀以兼容存量断言。
    """
    if isinstance(amount, bool):
        raise ValueError(f"金额类型无效 amount={amount!r}")
    try:
        value = Decimal(str(amount).strip())
    except (InvalidOperation, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"金额格式无效 amount={amount!r}") from exc
    if not value.is_finite():
        raise ValueError(f"金额非有限数值 amount={amount!r}")
    if value < 0:
        raise ValueError(f"金额不能为负 amount={amount!r}")
    try:
        quantized = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"金额格式无效 amount={amount!r}") from exc
    return int(quantized * 100)


def fen_to_yuan(amount_fen: int) -> float:
    """把金额（分）换算为元，仅用于数据库浮点列与展示传输。

    账务判定一律使用整数分，本函数不参与任何金额比较与结算。
    """
    return amount_fen / 100


def fen_to_yuan_str(amount_fen: int) -> str:
    """把金额（分）换算为规范十进制元字符串，REAL 兼容边界适配器。

    持久化业务路径如需与 SQLite REAL 列互操作，须经本函数产生两位
    小数字符串，保证分→元→分精确往返；账务比较仍只用整数分。
    迁移计划：后续将订单/流水金额列改为整数分存储后，本函数仅保留
    给展示层使用，REAL 列只作只读传输形态。
    """
    return str(
        (Decimal(int(amount_fen)) / Decimal(100)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    )


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
