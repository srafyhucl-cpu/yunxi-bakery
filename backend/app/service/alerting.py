"""
企业微信机器人告警模块。

在关键异常发生时通过企微群机器人 Webhook 推送告警消息。
支持多级别告警、防刷机制、Markdown 格式化。
"""

import time
from collections.abc import Callable, Coroutine
from enum import Enum

from app.config import settings
from app.logger import setup_logger
import httpx

logger = setup_logger()


class AlertLevel(str, Enum):
    """告警级别。"""

    CRITICAL = "CRITICAL"  # 服务不可用 / 数据丢失
    WARNING = "WARNING"  # 降级 / 可恢复异常
    INFO = "INFO"  # 状态变更通知


# ── 告警级别对应的企业微信 Markdown 颜色 ────────────────────────────────────────
_LEVEL_COLORS: dict[AlertLevel, str] = {
    AlertLevel.CRITICAL: "#FF0000",
    AlertLevel.WARNING: "#FFA500",
    AlertLevel.INFO: "#008000",
}

# 同一告警来源的最短间隔（秒），防止刷屏
_RATE_LIMIT_SECONDS: float = 300.0

# 防刷记录：{key: last_alert_timestamp}
_rate_limit_store: dict[str, float] = {}


class AlertService:
    """企业微信群机器人告警服务。

    使用示例:
        alert_service = AlertService()
        await alert_service.alert(
            AlertLevel.WARNING,
            "LLM 调用连续失败",
            "chat.py handle_message 连续 3 次请求超时"
        )
    """

    def __init__(self, webhook_url: str | None = None):
        self._webhook_url = webhook_url or settings.WECOM_ROBOT_WEBHOOK
        self._enabled = bool(self._webhook_url)

    def _is_rate_limited(self, key: str) -> bool:
        """检查告警是否在冷却期内。"""
        now = time.monotonic()
        last = _rate_limit_store.get(key, 0.0)
        if now - last < _RATE_LIMIT_SECONDS:
            return True
        _rate_limit_store[key] = now
        return False

    def _format_markdown(
        self,
        level: AlertLevel,
        title: str,
        detail: str,
        extra: dict[str, str] | None = None,
    ) -> str:
        """构建企微 Markdown 格式告警消息。"""
        color = _LEVEL_COLORS.get(level, "#808080")
        lines = [
            f'## <font color="{color}">【芸熙烘焙 {level.value}】</font>',
            f"**{title}**",
            "",
            detail,
        ]
        if extra:
            lines.append("")
            for k, v in extra.items():
                lines.append(f"> {k}: {v}")
        lines.append("")
        lines.append(f"> 告警时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        return "\n".join(lines)

    async def alert(
        self,
        level: AlertLevel,
        title: str,
        detail: str,
        *,
        key: str | None = None,
        extra: dict[str, str] | None = None,
    ) -> None:
        """发送告警。

        Args:
            level: 告警级别
            title: 告警标题
            detail: 告警详情
            key: 防刷 key（默认使用 title，同一 key 300 秒内不重复发送）
            extra: 附加字段（如 trace_id、session_id）
        """
        if not self._enabled:
            logger.debug("企业微信 Webhook 未配置，跳过告警: %s", title)
            return

        rate_key = key or title
        if self._is_rate_limited(rate_key):
            logger.debug("告警已被限流: %s", rate_key)
            return

        content = self._format_markdown(level, title, detail, extra)
        payload = {
            "msgtype": "markdown",
            "markdown": {"content": content},
        }

        try:
            async with httpx.AsyncClient(timeout=10, trust_env=False) as client:
                response = await client.post(self._webhook_url, json=payload)
            if response.status_code == 200:
                logger.info("企微告警已发送: [%s] %s", level.value, title)
            else:
                logger.error(
                    "企微告警发送失败 HTTP %d: %s",
                    response.status_code,
                    response.text[:200],
                )
        except Exception as exc:
            logger.error("企微告警网络异常: %s", exc)

    def create_threshold_alerter(
        self,
        level: AlertLevel,
        title: str,
        threshold: int = 3,
        window_seconds: float = 60.0,
    ) -> Callable[[str], Coroutine[None, None, None]]:
        """创建阈值告警器：在指定时间窗口内累计超过阈值时触发告警。

        Args:
            level: 告警级别
            title: 告警标题
            threshold: 触发阈值（默认 3 次）
            window_seconds: 时间窗口（默认 60 秒）

        Returns:
            异步函数，每次调用传入 detail 字符串，当窗口内累计超过阈值时触发告警。
        """
        counter: list[tuple[float, str]] = []

        async def _alerter(detail: str) -> None:
            now = time.monotonic()
            # 清理过期记录
            counter[:] = [(t, d) for t, d in counter if now - t < window_seconds]
            counter.append((now, detail))
            if len(counter) >= threshold:
                # 汇总最近 N 次 detail
                recent_details = "\n".join(f"- {d}" for _, d in counter[-threshold:])
                await self.alert(
                    level, title, f"最近 {threshold} 次异常:\n{recent_details}"
                )
                counter.clear()

        return _alerter


# ── 全局单例 ──────────────────────────────────────────────────────────────────
alert_service = AlertService()
