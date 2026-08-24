"""知识配置后台的向量同步服务。"""

from __future__ import annotations

import asyncio
import json
import time

from app.logger import setup_logger
from app.models.content_change_history import (
    ChangeAction,
    ChangeEntityType,
    ChangeStatus,
    ContentChangeHistoryCreate,
    SyncSource,
)
from app.models.knowledge import KnowledgeEntry, VectorSyncStatus
from app.repository.content_change_history_repo import ContentChangeHistoryRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.service.embedding_search import EmbeddingSearcher

logger = setup_logger()


def now_str() -> str:
    """返回统一的本地时间字符串。"""
    return time.strftime("%Y-%m-%d %H:%M:%S")


class KnowledgeSyncService:
    """负责将后台知识条目同步到向量索引，并回写状态。"""

    def __init__(
        self,
        knowledge_repo: KnowledgeRepo,
        history_repo: ContentChangeHistoryRepo,
        embedding_searcher: EmbeddingSearcher,
    ) -> None:
        self._knowledge_repo = knowledge_repo
        self._history_repo = history_repo
        self._embedding_searcher = embedding_searcher

    async def sync_admin_entry(
        self,
        entry: KnowledgeEntry,
        *,
        action: str,
        operator: str,
        retry_increment: bool = False,
    ) -> KnowledgeEntry:
        """同步后台知识条目，并返回最新状态。"""
        await self._knowledge_repo.mark_vector_sync_status(
            entry.id,
            status=VectorSyncStatus.SYNCING,
            retry_increment=retry_increment,
        )
        try:
            if entry.is_active:
                model = self._embedding_searcher._get_model()
                vector_data = (
                    await asyncio.to_thread(
                        model.encode,
                        [f"{entry.title} {entry.content}"],
                        normalize_embeddings=True,
                    )
                )[0]
                vector = (
                    vector_data.tolist()
                    if hasattr(vector_data, "tolist")
                    else list(vector_data)
                )
                await self._embedding_searcher.upsert_one(self._doc_key(entry), vector)
            else:
                await self._embedding_searcher.delete_one(self._doc_key(entry))

            synced_at = now_str()
            await self._knowledge_repo.mark_vector_sync_status(
                entry.id,
                status=VectorSyncStatus.SUCCESS,
                synced_at=synced_at,
            )
            await self._history_repo.add(
                ContentChangeHistoryCreate(
                    entity_type=ChangeEntityType.KNOWLEDGE,
                    entity_key=self._doc_key(entry),
                    category=entry.category,
                    title=entry.title,
                    source=SyncSource.ADMIN_MANUAL,
                    source_ref=str(entry.id),
                    action=action,
                    status=ChangeStatus.SUCCESS,
                    change_summary_json=self._build_summary(
                        entry, operator, synced_at, ""
                    ),
                    occurred_at=synced_at,
                )
            )
        except Exception as exc:
            error_message = str(exc)
            logger.error("知识条目同步向量失败: id=%s err=%s", entry.id, error_message)
            await self._knowledge_repo.mark_vector_sync_status(
                entry.id,
                status=VectorSyncStatus.FAILED,
                error_message=error_message,
            )
            await self._history_repo.add(
                ContentChangeHistoryCreate(
                    entity_type=ChangeEntityType.KNOWLEDGE,
                    entity_key=self._doc_key(entry),
                    category=entry.category,
                    title=entry.title,
                    source=SyncSource.ADMIN_MANUAL,
                    source_ref=str(entry.id),
                    action=action,
                    status=ChangeStatus.FAILED,
                    change_summary_json=self._build_summary(
                        entry, operator, "", error_message
                    ),
                    error_type=type(exc).__name__,
                    error_message=error_message,
                    occurred_at=now_str(),
                )
            )
        latest_entry = await self._knowledge_repo.get_by_id(entry.id)
        if latest_entry is None:
            raise RuntimeError(f"知识条目不存在: {entry.id}")
        return latest_entry

    async def sync_all_pending(self) -> dict:
        """批量同步所有 pending/failed 状态的知识条目，返回 {total, success, failed}。"""
        entries = await self._knowledge_repo.get_pending_sync_entries()
        total = len(entries)
        if not total:
            logger.info("批量向量同步：无待同步条目，跳过")
            return {"total": 0, "success": 0, "failed": 0}

        success_count = 0
        failed_count = 0
        logger.info("批量向量同步开始，共 %d 条待同步条目", total)
        for entry in entries:
            try:
                updated = await self.sync_admin_entry(
                    entry,
                    action=ChangeAction.SYNC_RETRY,
                    operator="system",
                )
                if updated.vector_sync_status == VectorSyncStatus.SUCCESS:
                    success_count += 1
                else:
                    failed_count += 1
            except Exception as exc:
                failed_count += 1
                logger.error("批量同步条目异常: id=%s err=%s", entry.id, exc)

        logger.info(
            "批量向量同步完成：成功 %d，失败 %d，共 %d 条",
            success_count,
            failed_count,
            total,
        )
        return {"total": total, "success": success_count, "failed": failed_count}

    @staticmethod
    def _doc_key(entry: KnowledgeEntry) -> str:
        return f"kb_{entry.id}"

    @staticmethod
    def _build_summary(
        entry: KnowledgeEntry,
        operator: str,
        synced_at: str,
        error_message: str,
    ) -> str:
        return json.dumps(
            {
                "content_type": entry.content_type,
                "is_active": 1 if entry.is_active else 0,
                "operator": operator,
                "synced_at": synced_at,
                "error_message": error_message,
            },
            ensure_ascii=False,
        )
