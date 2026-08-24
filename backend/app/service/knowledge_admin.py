"""知识配置后台服务。"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from app.models.content_change_history import (
    ChangeAction,
    ChangeEntityType,
    SyncSource,
    WriteResult,
)
from app.models.knowledge import (
    KnowledgeAudience,
    KnowledgeContentType,
    KnowledgeEntry,
    KnowledgeReviewStatus,
)
from app.models.knowledge_admin import KnowledgeAdminDraft, KnowledgeCategorySuggestion
from app.repository.content_change_history_repo import ContentChangeHistoryRepo
from app.repository.knowledge_admin_repo import KnowledgeAdminRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.service.knowledge_sync import KnowledgeSyncService

DEFAULT_PRIORITY = 50
MAX_KEYWORDS_LENGTH = 200
MIN_PRIORITY = 0
MAX_PRIORITY = 100

_FAQ_HINTS = (
    "吗",
    "怎么",
    "如何",
    "能否",
    "可以",
    "是否",
    "多久",
    "几点",
    "多少",
    "什么时候",
)
_RULE_HINTS = (
    "规则",
    "退款",
    "售后",
    "改期",
    "配送",
    "预订",
    "定制",
    "发票",
    "补差",
    "需提前",
    "不支持",
)
_SCRIPT_HINTS = (
    "您好",
    "亲",
    "抱歉",
    "建议您",
    "请您",
    "欢迎",
    "推荐您",
    "麻烦您",
    "辛苦您",
    "可以这样回复",
)


class KnowledgeAdminService:
    """负责后台知识条目的查询、编辑和分类建议。"""

    def __init__(
        self,
        knowledge_repo: KnowledgeRepo,
        admin_repo: KnowledgeAdminRepo,
        history_repo: ContentChangeHistoryRepo,
        sync_service: KnowledgeSyncService,
    ) -> None:
        self._knowledge_repo = knowledge_repo
        self._admin_repo = admin_repo
        self._history_repo = history_repo
        self._sync_service = sync_service

    async def list_entries(
        self,
        *,
        content_type: str = "",
        is_active: str = "",
        vector_status: str = "",
        keyword: str = "",
        limit: int = 20,
        offset: int = 0,
    ) -> list[KnowledgeEntry]:
        return await self._admin_repo.list_admin_entries(
            content_type=content_type,
            is_active=is_active,
            vector_status=vector_status,
            keyword=keyword,
            limit=limit,
            offset=offset,
        )

    async def count_entries(
        self,
        *,
        content_type: str = "",
        is_active: str = "",
        vector_status: str = "",
        keyword: str = "",
    ) -> int:
        return await self._admin_repo.count_admin_entries(
            content_type=content_type,
            is_active=is_active,
            vector_status=vector_status,
            keyword=keyword,
        )

    async def get_entry_detail(self, entry_id: int) -> dict | None:
        entry = await self._knowledge_repo.get_by_id(entry_id)
        if entry is None or entry.content_type == KnowledgeContentType.PRODUCT:
            return None
        history = await self._history_repo.list_for_entity(
            entity_type=ChangeEntityType.KNOWLEDGE,
            entity_key=f"kb_{entry.id}",
            limit=5,
        )
        return {
            "entry": entry,
            "history": [
                {
                    "id": item.id,
                    "action": item.action,
                    "status": item.status,
                    "occurred_at": item.occurred_at,
                    "error_message": item.error_message,
                    "summary": self._loads_json(item.change_summary_json),
                }
                for item in history
            ],
        }

    async def create_entry(
        self, draft: KnowledgeAdminDraft, *, operator: str
    ) -> KnowledgeEntry:
        normalized = self._normalize_draft(draft)
        suggestion = self.suggest_category(
            title=normalized.title, content=normalized.content
        )
        entry_id = await self._admin_repo.create_admin_entry(
            category=self._map_category(normalized.content_type),
            content_type=normalized.content_type,
            title=normalized.title,
            content=normalized.content,
            keywords=normalized.keywords,
            priority=normalized.priority,
            is_active=normalized.is_active,
            content_origin="admin_console",
            created_by=operator,
            updated_by=operator,
            suggested_category=suggestion.content_type,
            suggest_reason=suggestion.reason,
            sync_source=SyncSource.ADMIN_MANUAL,
            vector_sync_status="pending",
            audience=normalized.audience,
            review_status=normalized.review_status,
            valid_from=normalized.valid_from,
            valid_until=normalized.valid_until,
            reviewed_by=self._reviewed_by(normalized, operator),
            reviewed_at=self._reviewed_at(normalized),
        )
        entry = await self._require_entry(entry_id)
        return await self._sync_service.sync_admin_entry(
            entry,
            action=ChangeAction.CREATE,
            operator=operator,
        )

    async def update_entry(
        self,
        entry_id: int,
        draft: KnowledgeAdminDraft,
        *,
        operator: str,
    ) -> KnowledgeEntry:
        existing = await self._require_entry(entry_id)
        normalized = self._normalize_draft(draft)
        suggestion = self.suggest_category(
            title=normalized.title, content=normalized.content
        )
        result = await self._admin_repo.update_admin_entry(
            entry_id,
            category=self._map_category(normalized.content_type),
            content_type=normalized.content_type,
            title=normalized.title,
            content=normalized.content,
            keywords=normalized.keywords,
            priority=normalized.priority,
            is_active=normalized.is_active,
            updated_by=operator,
            suggested_category=suggestion.content_type,
            suggest_reason=suggestion.reason,
            sync_source=SyncSource.ADMIN_MANUAL,
            sync_ref=str(existing.id),
            vector_sync_status="pending",
            audience=normalized.audience,
            review_status=normalized.review_status,
            valid_from=normalized.valid_from,
            valid_until=normalized.valid_until,
            reviewed_by=self._reviewed_by(normalized, operator, existing.reviewed_by),
            reviewed_at=self._reviewed_at(normalized, existing.reviewed_at),
        )
        if result == WriteResult.SKIPPED:
            return await self._require_entry(entry_id)
        entry = await self._require_entry(entry_id)
        return await self._sync_service.sync_admin_entry(
            entry,
            action=ChangeAction.UPDATE,
            operator=operator,
        )

    async def toggle_active(self, entry_id: int, *, operator: str) -> KnowledgeEntry:
        entry = await self._require_entry(entry_id)
        await self._admin_repo.update_active(
            entry_id,
            not entry.is_active,
            sync_source=SyncSource.ADMIN_MANUAL,
            sync_ref=str(entry_id),
        )
        toggled = await self._require_entry(entry_id)
        action = ChangeAction.ACTIVATE if toggled.is_active else ChangeAction.DEACTIVATE
        return await self._sync_service.sync_admin_entry(
            toggled,
            action=action,
            operator=operator,
        )

    async def retry_sync(self, entry_id: int, *, operator: str) -> KnowledgeEntry:
        entry = await self._require_entry(entry_id)
        return await self._sync_service.sync_admin_entry(
            entry,
            action=ChangeAction.SYNC_RETRY,
            operator=operator,
            retry_increment=True,
        )

    def suggest_category(
        self, *, title: str, content: str
    ) -> KnowledgeCategorySuggestion:
        merged = f"{title}\n{content}".strip()
        if self._matches_any(merged, _RULE_HINTS):
            return KnowledgeCategorySuggestion(
                content_type=KnowledgeContentType.RULE,
                label="门店规则",
                reason="检测到退款、配送、预订或限制类关键词，更像稳定规则说明。",
            )
        if self._matches_any(merged, _SCRIPT_HINTS):
            return KnowledgeCategorySuggestion(
                content_type=KnowledgeContentType.SCRIPT,
                label="回复话术",
                reason="检测到安抚、引导、推荐等表达，更像给 AI 的回复说法。",
            )
        if "？" in merged or "?" in merged or self._matches_any(merged, _FAQ_HINTS):
            return KnowledgeCategorySuggestion(
                content_type=KnowledgeContentType.FAQ,
                label="常见问答",
                reason="内容更接近用户提问和标准回答，适合放入常见问答。",
            )
        return KnowledgeCategorySuggestion(
            content_type=KnowledgeContentType.FAQ,
            label="常见问答",
            reason="未命中明显规则或话术特征，默认建议按常见问答管理。",
        )

    async def _require_entry(self, entry_id: int) -> KnowledgeEntry:
        entry = await self._knowledge_repo.get_by_id(entry_id)
        if entry is None or entry.content_type == KnowledgeContentType.PRODUCT:
            raise ValueError(f"知识条目不存在: {entry_id}")
        return entry

    def _normalize_draft(self, draft: KnowledgeAdminDraft) -> KnowledgeAdminDraft:
        title = draft.title.strip()
        content = draft.content.strip()
        keywords = self._normalize_keywords(draft.keywords, title, content)
        content_type = (draft.content_type or "").strip()
        audience = (draft.audience or KnowledgeAudience.ALL.value).strip()
        review_status = (
            draft.review_status or KnowledgeReviewStatus.PUBLISHED.value
        ).strip()
        valid_from = draft.valid_from.strip()
        valid_until = draft.valid_until.strip()
        if not title:
            raise ValueError("标题不能为空")
        if not content:
            raise ValueError("正文不能为空")
        if content_type not in {
            KnowledgeContentType.FAQ,
            KnowledgeContentType.RULE,
            KnowledgeContentType.SCRIPT,
        }:
            raise ValueError("分类不能为空")
        if audience not in {
            KnowledgeAudience.ALL.value,
            KnowledgeAudience.CUSTOMER.value,
            KnowledgeAudience.EMPLOYEE.value,
        }:
            raise ValueError("可见范围不合法")
        if review_status not in {
            KnowledgeReviewStatus.DRAFT.value,
            KnowledgeReviewStatus.PUBLISHED.value,
            KnowledgeReviewStatus.ARCHIVED.value,
        }:
            raise ValueError("审核状态不合法")
        if valid_from and valid_until and valid_from > valid_until:
            raise ValueError("生效开始时间不能晚于截止时间")
        if len(keywords) > MAX_KEYWORDS_LENGTH:
            raise ValueError("关键词过长，请控制在 200 字以内")
        if draft.priority < MIN_PRIORITY or draft.priority > MAX_PRIORITY:
            raise ValueError("优先级必须在 0 到 100 之间")
        return KnowledgeAdminDraft(
            title=title,
            content=content,
            content_type=content_type,
            keywords=keywords,
            priority=draft.priority if draft.priority is not None else DEFAULT_PRIORITY,
            is_active=draft.is_active,
            audience=audience,
            review_status=review_status,
            valid_from=valid_from,
            valid_until=valid_until,
        )

    @staticmethod
    def _normalize_keywords(keywords: str, title: str, content: str) -> str:
        raw = keywords.strip()
        if raw:
            return raw
        base_words = [title]
        tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", content[:80])
        base_words.extend(tokens[:5])
        deduped: list[str] = []
        for item in base_words:
            clean = item.strip()
            if clean and clean not in deduped:
                deduped.append(clean)
        return " ".join(deduped)

    @staticmethod
    def _map_category(content_type: str) -> str:
        if content_type == KnowledgeContentType.RULE:
            return "policy"
        if content_type == KnowledgeContentType.SCRIPT:
            return "store_info"
        return "faq"

    @staticmethod
    def _reviewed_by(
        draft: KnowledgeAdminDraft, operator: str, fallback: str = ""
    ) -> str:
        if draft.review_status == KnowledgeReviewStatus.PUBLISHED.value:
            return operator
        return fallback

    @staticmethod
    def _reviewed_at(draft: KnowledgeAdminDraft, fallback: str = "") -> str:
        if draft.review_status == KnowledgeReviewStatus.PUBLISHED.value:
            return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        return fallback

    @staticmethod
    def _matches_any(text: str, keywords: tuple[str, ...]) -> bool:
        return any(keyword in text for keyword in keywords)

    @staticmethod
    def _loads_json(raw: str) -> dict:
        try:
            return json.loads(raw or "{}")
        except json.JSONDecodeError:
            return {}
