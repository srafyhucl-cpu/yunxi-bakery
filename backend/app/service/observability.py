"""数据观察台服务与内容变更日志能力。"""

from __future__ import annotations

import json
from datetime import datetime

from app.models.content_change_history import (
    ChangeEntityType,
    ChangeStatus,
    ContentChangeHistoryCreate,
)
from app.repository.content_change_history_repo import ContentChangeHistoryRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.repository.youzan_webhook_event_repo import YouzanWebhookEventRepo
from app.service.observability_summary import build_operation_summary


def now_str() -> str:
    """返回统一格式的本地时间字符串。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class ContentChangeLogger:
    """封装内容变更历史写入。"""

    def __init__(self, history_repo: ContentChangeHistoryRepo) -> None:
        self._history_repo = history_repo

    async def log_success(
        self,
        *,
        entity_type: str,
        entity_key: str,
        category: str,
        title: str,
        source: str,
        action: str,
        change_summary: dict,
        source_ref: str = "",
        session_id: str = "",
        webhook_msg_id: str = "",
        occurred_at: str = "",
    ) -> int:
        """记录成功写库的历史事件。"""
        return await self._history_repo.add(
            ContentChangeHistoryCreate(
                entity_type=entity_type,
                entity_key=entity_key,
                category=category,
                title=title,
                source=source,
                source_ref=source_ref,
                session_id=session_id,
                webhook_msg_id=webhook_msg_id,
                action=action,
                status=ChangeStatus.SUCCESS,
                change_summary_json=json.dumps(change_summary, ensure_ascii=False),
                occurred_at=occurred_at or now_str(),
            )
        )

    async def log_failed(
        self,
        *,
        entity_type: str,
        entity_key: str,
        category: str,
        title: str,
        source: str,
        action: str,
        error_type: str,
        error_message: str,
        change_summary: dict | None = None,
        source_ref: str = "",
        session_id: str = "",
        webhook_msg_id: str = "",
        occurred_at: str = "",
    ) -> int:
        """记录失败历史事件。"""
        return await self._history_repo.add(
            ContentChangeHistoryCreate(
                entity_type=entity_type,
                entity_key=entity_key,
                category=category,
                title=title,
                source=source,
                source_ref=source_ref,
                session_id=session_id,
                webhook_msg_id=webhook_msg_id,
                action=action,
                status=ChangeStatus.FAILED,
                change_summary_json=json.dumps(
                    change_summary or {}, ensure_ascii=False
                ),
                error_type=error_type,
                error_message=error_message,
                occurred_at=occurred_at or now_str(),
            )
        )


class ObservabilityService:
    """组装数据观察台所需的当前内容、历史与 webhook 审计数据。"""

    def __init__(
        self,
        knowledge_repo: KnowledgeRepo,
        product_repo: YouzanProductRepo,
        history_repo: ContentChangeHistoryRepo,
        webhook_repo: YouzanWebhookEventRepo,
    ) -> None:
        self._knowledge_repo = knowledge_repo
        self._product_repo = product_repo
        self._history_repo = history_repo
        self._webhook_repo = webhook_repo

    async def list_current_content(
        self,
        *,
        view: str = "all",
        category: str = "",
        keyword: str = "",
        product_status: str = "",
        limit: int = 30,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """返回当前内容页所需的数据。"""
        entries = await self._knowledge_repo.list_current_entries(
            category=category,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
        total = await self._knowledge_repo.count_current_entries(
            category=category,
            keyword=keyword,
        )
        return [self._format_knowledge_item(entry) for entry in entries], total

    async def get_history(
        self,
        *,
        date_from: str = "",
        date_to: str = "",
        source: str = "",
        status: str = "",
        entity_type: str = "",
        keyword: str = "",
        limit: int = 30,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """返回回写历史页数据。"""
        entries = await self._history_repo.list_entries(
            date_from=date_from,
            date_to=date_to,
            source=source,
            status=status,
            entity_type=entity_type,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
        total = await self._history_repo.count_entries(
            date_from=date_from,
            date_to=date_to,
            source=source,
            status=status,
            entity_type=entity_type,
            keyword=keyword,
        )
        return [self._format_history_entry(entry) for entry in entries], total

    async def get_history_detail(self, entry_id: int) -> dict | None:
        """返回单条回写历史详情。"""
        entry = await self._history_repo.get_by_id(entry_id)
        return self._format_history_entry(entry) if entry else None

    async def get_webhooks(
        self,
        *,
        date_from: str = "",
        date_to: str = "",
        status: str = "",
        event_type: str = "",
        keyword: str = "",
        limit: int = 30,
        offset: int = 0,
    ) -> tuple[list[dict], int]:
        """返回 webhook 审计页数据。"""
        entries = await self._webhook_repo.list_events(
            date_from=date_from,
            date_to=date_to,
            status=status,
            event_type=event_type,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )
        total = await self._webhook_repo.count_events(
            date_from=date_from,
            date_to=date_to,
            status=status,
            event_type=event_type,
            keyword=keyword,
        )
        return [self._format_webhook_entry(entry) for entry in entries], total

    async def get_webhook_detail(self, event_id: int) -> dict | None:
        """返回单条 webhook 审计详情。"""
        entry = await self._webhook_repo.get_by_id(event_id)
        return self._format_webhook_entry(entry) if entry else None

    async def get_summary(self) -> dict:
        """返回上线值守摘要。"""
        return await build_operation_summary(self._history_repo, self._webhook_repo)

    def _format_knowledge_item(self, entry) -> dict:
        category = (
            entry.category.value
            if hasattr(entry.category, "value")
            else str(entry.category)
        )
        return {
            "entity_type": ChangeEntityType.KNOWLEDGE,
            "entity_key": str(entry.id),
            "title": entry.title,
            "subtitle": entry.keywords,
            "category": category,
            "status_text": "启用" if entry.is_active else "停用",
            "is_active": entry.is_active,
            "updated_at": entry.updated_at,
            "last_sync_source": entry.last_sync_source,
            "last_sync_ref": entry.last_sync_ref,
            "summary": [
                f"分类: {category}",
                f"优先级: {entry.priority}",
                f"关键词: {entry.keywords or '-'}",
            ],
            "details": [
                {"label": "标题", "value": entry.title},
                {"label": "正文", "value": entry.content},
                {"label": "关联有赞商品", "value": entry.youzan_item_id or "-"},
            ],
        }

    def _format_history_entry(self, entry) -> dict:
        summary = self._loads_json(entry.change_summary_json)
        return {
            "id": entry.id,
            "entity_type": entry.entity_type,
            "entity_key": entry.entity_key,
            "category": entry.category,
            "title": entry.title,
            "source": entry.source,
            "source_ref": entry.source_ref,
            "session_id": entry.session_id,
            "webhook_msg_id": entry.webhook_msg_id,
            "webhook_event_type": getattr(entry, "webhook_event_type", ""),
            "action": entry.action,
            "status": entry.status,
            "error_type": entry.error_type,
            "error_message": entry.error_message,
            "occurred_at": entry.occurred_at,
            "summary_lines": self._summary_lines(summary),
            "details": summary,
        }

    def _format_webhook_entry(self, entry: dict) -> dict:
        payload_summary = self._loads_json(entry.get("payload_summary_json", "{}"))
        return {
            "id": entry["id"],
            "msg_id": entry["msg_id"],
            "event_type": entry["event_type"],
            "business_type": entry["business_type"],
            "business_key": entry["business_key"],
            "status": entry["status"],
            "process_stage": entry["process_stage"],
            "error_type": entry["error_type"],
            "error_message": entry["error_message"],
            "received_at": entry["received_at"],
            "duration_ms": entry["duration_ms"],
            "summary_lines": self._summary_lines(payload_summary),
            "details": payload_summary,
        }

    def _json_to_lines(self, raw: str) -> str:
        parsed_data = self._loads_json(raw)
        if isinstance(parsed_data, list):
            lines = [self._compact_value(item) for item in parsed_data]
            return "\n".join(lines) if lines else "-"
        if isinstance(parsed_data, dict):
            return "\n".join(
                f"{key}: {self._compact_value(value)}"
                for key, value in parsed_data.items()
            )
        return self._compact_value(parsed_data)

    def _summary_lines(self, data: dict) -> list[str]:
        return [f"{key}: {self._compact_value(value)}" for key, value in data.items()]

    def _loads_json(self, raw: str) -> dict | list | str:
        try:
            value = json.loads(raw or "{}")
        except Exception:
            return {"raw": raw}
        return value

    def _compact_value(self, value) -> str:
        if isinstance(value, dict):
            return "；".join(
                f"{key}={self._compact_value(item)}" for key, item in value.items()
            )
        if isinstance(value, list):
            return "；".join(self._compact_value(item) for item in value)
        return str(value)


def build_product_change_summary(
    *,
    item_id: int,
    title: str,
    alias: str,
    price_fen: int,
    stock: int,
    is_active: int,
    tags: str,
    updated_at: str,
    knowledge_result: str = "",
    product_result: str = "",
    old_price_fen: int | None = None,
    old_stock: int | None = None,
) -> dict:
    """构造商品回写历史摘要。"""
    summary = {
        "item_id": item_id,
        "title": title,
        "alias": alias,
        "price_fen": price_fen,
        "stock": stock,
        "is_active": is_active,
        "tags": tags,
        "product_write_result": product_result,
        "knowledge_write_result": knowledge_result,
        "updated_at": updated_at,
    }
    if old_price_fen is not None:
        summary["old_price_fen"] = old_price_fen
    if old_stock is not None:
        summary["old_stock"] = old_stock
    return summary


def build_knowledge_change_summary(
    *,
    title: str,
    category: str,
    priority: int,
    is_active: bool,
) -> dict:
    """构造知识条目回写历史摘要。"""
    return {
        "title": title,
        "category": category,
        "priority": priority,
        "is_active": is_active,
    }
