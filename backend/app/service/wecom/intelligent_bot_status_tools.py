"""企微智能机器人状态与排障只读工具服务。"""

from collections.abc import Callable
from typing import Any

from app.logger import setup_logger
from app.service.wecom.intelligent_bot_ops_format import (
    compact_webhook,
    offline_review_line,
    offline_review_next_action,
    ops_summary_line,
    webhook_line,
)
from app.service.wecom.intelligent_bot_plugin import extract_text
from app.service.wecom.intelligent_bot_tool_response import (
    extract_limit,
    failed,
    ok_response,
    unavailable,
)

logger = setup_logger()
OfflineSummaryProvider = Callable[[], Any]


class WeComBotStatusToolService:
    """封装观察台、同步排障和离线复盘状态工具。"""

    def __init__(
        self,
        *,
        observability_service: Any = None,
        offline_summary_provider: OfflineSummaryProvider | None = None,
    ) -> None:
        self._observability_service = observability_service
        self._offline_summary_provider = offline_summary_provider

    def set_offline_summary_provider(
        self,
        provider: OfflineSummaryProvider,
    ) -> None:
        """注入离线复盘摘要读取器。"""
        self._offline_summary_provider = provider

    async def summarize_ops(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._observability_service is None:
            return unavailable("ops_summary", "经营观察摘要")
        try:
            summary = await self._observability_service.get_summary()
        except Exception as exc:
            logger.error("企微观察台摘要工具失败 err=%s", exc)
            return failed("ops_summary", "观察台摘要读取失败，请稍后重试。")
        return ok_response(
            "ops_summary",
            extract_text(payload) or "summary",
            ops_summary_line(summary),
            status=str(summary.get("status", "")),
            counts=summary.get("counts", {}),
            nextAction="需要关注时，优先查看 Webhook 失败记录和内容回写历史。",
        )

    async def summarize_integrations(self, payload: dict[str, Any]) -> dict[str, Any]:
        query = extract_text(payload)
        limit = extract_limit(payload)
        if self._observability_service is None:
            return unavailable("integration_status", "同步排障")
        try:
            webhooks, total = await self._observability_service.get_webhooks(
                status="failed",
                keyword=query,
                limit=limit,
            )
        except Exception as exc:
            logger.error("企微同步排障工具失败 query=%s err=%s", query, exc)
            return failed("integration_status", "同步排障读取失败，请稍后重试。")
        safe_webhooks = [compact_webhook(item) for item in webhooks]
        webhooks_text = "\n".join(webhook_line(item) for item in safe_webhooks)
        return ok_response(
            "integration_status",
            query or "failed",
            f"找到 {total} 条失败 webhook，返回 {len(webhooks)} 条。",
            webhooks=safe_webhooks,
            webhooksText=webhooks_text or "当前没有匹配的失败 webhook。",
            nextAction="如连续失败，请进入观察台查看详情并按 event_type 排查。",
        )

    async def summarize_offline_review(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._offline_summary_provider is None:
            return unavailable("offline_review_summary", "离线复盘摘要")
        summary = self._offline_summary_provider()
        if summary is None:
            return failed("offline_review_summary", "离线复盘调度器尚未启动或未启用。")
        return ok_response(
            "offline_review_summary",
            extract_text(payload) or "latest",
            offline_review_line(summary),
            startedAt=str(getattr(summary, "started_at", "")),
            finishedAt=str(getattr(summary, "finished_at", "")),
            ran=bool(getattr(summary, "ran", False)),
            skippedReason=str(getattr(summary, "skipped_reason", "")),
            reviewCount=int(getattr(summary, "review_count", 0) or 0),
            gapCount=int(getattr(summary, "gap_count", 0) or 0),
            profileCount=int(getattr(summary, "profile_count", 0) or 0),
            totalProcessed=int(getattr(summary, "total_processed", 0) or 0),
            nextAction=offline_review_next_action(summary),
        )
