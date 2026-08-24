"""
有赞系统事件分发器。

接收来自 ChatService 的有赞 Webhook 系统事件，解析 msg 字段后
按事件类型分发至 event_trade / event_item 专项处理模块。
"""

import json
import urllib.parse

from app.logger import setup_logger
from app.models.youzan_webhook_event import (
    YouzanWebhookEventUpdate,
    YouzanWebhookStatus,
)
from app.repository.youzan_webhook_event_repo import YouzanWebhookEventRepo
from app.service.youzan.client import YouzanClient
from app.service.youzan.event_item import handle_item_event
from app.service.youzan.event_member import MEMBER_EVENT_TYPES, handle_member_event
from app.service.youzan.event_trade import handle_trade_event
from app.service.youzan.webhook_payload import parse_item_id

logger = setup_logger()

# 预留废弃事件集合（目前为空，ITEM_INFO 已恢复，真实推送 msg 大概率含 item_id）
_DEPRECATED_EVENT_TYPES: frozenset[str] = frozenset()

# 有赞新式库存/销量变更事件：item_id 直接在 payload 顶层，无 msg 字段
_SKU_STOCK_UPDATE_EVENT = "youzan_item_skustockorsoldnumupdated"


class YouzanEventHandler:
    """有赞系统事件处理器（商品 + 交易 Webhook 双轨合流分发器）。"""

    def __init__(
        self,
        db,
        knowledge_retriever,
        youzan_client: YouzanClient,
        audit_repo: YouzanWebhookEventRepo | None = None,
    ) -> None:
        self._db = db
        self._knowledge = knowledge_retriever
        self._youzan_client = youzan_client
        self._audit_repo = audit_repo

    async def handle_system_event(
        self,
        payload: dict,
        event_type: str,
        updated_at_str: str,
        msg_id: str,
        audit_id: int | None = None,
    ) -> None:
        """
        解析并分发有赞系统事件至对应处理模块。

        参数：
            payload: 有赞 Webhook 原始 payload
            event_type: 由 webhook 网关解析的事件类型（优先取 header event-type）
            updated_at_str: 事件时间字符串（格式 %Y-%m-%d %H:%M:%S）
            msg_id: 消息去重 ID
        """
        if event_type in _DEPRECATED_EVENT_TYPES:
            logger.info(
                "有赞已废弃事件，跳过处理: type=%s msg_id=%s", event_type, msg_id
            )
            await self._mark_skipped(audit_id, "deprecated_event", event_type)
            return

        raw_msg = payload.get("msg")
        if isinstance(raw_msg, dict):
            msg_obj = raw_msg
        else:
            msg_str = urllib.parse.unquote(raw_msg or "{}")
            try:
                msg_obj = json.loads(msg_str)
            except Exception as exc:
                # msg 解析失败不立即返回，降级为空字典让后续 fallback（如 ITEM_INFO 的 payload.id）兜底
                logger.warning(
                    "有赞系统事件 msg JSON 解析失败，降级为空字典继续: type=%s msg_id=%s err=%s",
                    event_type,
                    msg_id,
                    exc,
                )
                msg_obj = {}
            if not isinstance(msg_obj, dict):
                logger.warning(
                    "有赞系统事件 msg 解析结果非字典，已重置: type=%s msg_id=%s val_type=%s",
                    event_type,
                    msg_id,
                    type(msg_obj).__name__,
                )
                msg_obj = {}

        event_type_lower = event_type.lower()
        if event_type_lower.startswith("trade_"):
            await handle_trade_event(
                db=self._db,
                youzan_client=self._youzan_client,
                event_type=event_type,
                msg_obj=msg_obj,
                updated_at_str=updated_at_str,
                audit_repo=self._audit_repo,
                audit_id=audit_id,
            )
        elif event_type_lower.startswith("item_"):
            item_id = parse_item_id(payload, msg_obj)
            if not item_id:
                # ITEM_INFO/ITEM_SKU_INFO 顶层 id 理论上可能是商品ID，由 parse_item_id 已做纯数字过滤
                logger.warning(
                    "有赞商品事件无法解析 item_id: type=%s msg_id=%s",
                    event_type,
                    msg_id,
                )
                await self._mark_skipped(audit_id, "missing_item_id", event_type)
                return
            # item_id 可能来自 payload.data 或 payload.id（msg_obj 内不含），
            # 统一回注 msg_obj 供下游 handle_item_event 复用，避免其二次解析失败而误跳过
            if not msg_obj.get("item_id"):
                msg_obj = {**msg_obj, "item_id": item_id}
            await handle_item_event(
                db=self._db,
                youzan_client=self._youzan_client,
                knowledge_retriever=self._knowledge,
                event_type=event_type,
                msg_obj=msg_obj,
                updated_at_str=updated_at_str,
                msg_id=msg_id,
                audit_repo=self._audit_repo,
                audit_id=audit_id,
            )
        elif event_type_lower in MEMBER_EVENT_TYPES:
            await handle_member_event(
                db=self._db,
                youzan_client=self._youzan_client,
                event_type=event_type,
                msg_obj=msg_obj,
                updated_at_str=updated_at_str,
                audit_repo=self._audit_repo,
                audit_id=audit_id,
                msg_id=msg_id,
            )
        elif event_type_lower == _SKU_STOCK_UPDATE_EVENT:
            item_id = parse_item_id(payload)
            if item_id:
                await handle_item_event(
                    db=self._db,
                    youzan_client=self._youzan_client,
                    knowledge_retriever=self._knowledge,
                    event_type=event_type,
                    msg_obj={"item_id": item_id},
                    updated_at_str=updated_at_str,
                    msg_id=msg_id,
                    audit_repo=self._audit_repo,
                    audit_id=audit_id,
                )
            else:
                logger.warning("商品规格库存更新事件缺少 item_id: msg_id=%s", msg_id)
                await self._mark_skipped(audit_id, "missing_item_id", event_type)
        else:
            logger.info(
                "有赞系统事件已接收，暂无处理器，已跳过: type=%s msg_id=%s",
                event_type,
                msg_id,
            )
            await self._mark_skipped(audit_id, "unknown_event_type", event_type)

    async def _mark_skipped(
        self, audit_id: int | None, error_type: str, event_type: str
    ) -> None:
        if self._audit_repo is None or audit_id is None:
            return
        await self._audit_repo.mark_result(
            audit_id,
            YouzanWebhookEventUpdate(
                status=YouzanWebhookStatus.SKIPPED,
                process_stage="dispatch_skipped",
                error_type=error_type,
                error_message=f"event_type={event_type}",
            ),
        )
