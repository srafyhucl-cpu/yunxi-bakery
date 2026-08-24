"""微信消息队列的通用后台 Worker 基类。"""

import asyncio
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from app.logger import setup_logger

logger = setup_logger()

MessageT = TypeVar("MessageT")


class BaseWeComMessageQueue(ABC, Generic[MessageT]):
    """封装队列 Worker 的启动、停止和异常隔离流程。"""

    def __init__(self, queue_max_size: int, queue_name: str) -> None:
        self._queue: asyncio.Queue[MessageT] = asyncio.Queue(maxsize=queue_max_size)
        self._worker_task: asyncio.Task[None] | None = None
        self._chat_service = None
        self._queue_name = queue_name
        self._persistent_mode = False
        self._stop_requested = False

    def start_worker(self, chat_service) -> None:
        """启动后台消费任务。"""
        if self._worker_task is not None and not self._worker_task.done():
            logger.warning("%s Worker 已在运行，跳过重复启动", self._queue_name)
            return

        self._chat_service = chat_service
        self._stop_requested = False
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("%s Worker 已启动", self._queue_name)

    async def stop(self) -> None:
        """停止后台 Worker。"""
        if self._worker_task is None or self._worker_task.done():
            return

        if self._persistent_mode:
            self._stop_requested = True
            await self._worker_task
            self._worker_task = None
            logger.info("%s Worker 已完成 drain 并停止", self._queue_name)
            return

        self._worker_task.cancel()
        try:
            await self._worker_task
        except asyncio.CancelledError:
            pass
        self._worker_task = None
        logger.info("%s Worker 已停止", self._queue_name)

    @property
    def queue_size(self) -> int:
        """当前队列中的待处理消息数量。"""
        return self._queue.qsize()

    async def _worker_loop(self) -> None:
        """持续消费队列，单条异常不影响后续消息。"""
        logger.info("%s Worker 开始运行", self._queue_name)
        while True:
            msg = await self._claim_persisted_message()
            if msg is not None:
                await self._process_persisted_message(msg)
                continue
            if self._persistent_mode and self._stop_requested:
                break
            try:
                if self._persistent_mode:
                    msg = await asyncio.wait_for(self._queue.get(), timeout=0.2)
                else:
                    msg = await self._queue.get()
            except asyncio.TimeoutError:
                continue
            except (asyncio.CancelledError, GeneratorExit):
                break

            try:
                await self._process_one(msg)
            except Exception as exc:
                logger.error(
                    "%s 消息处理异常 %s err=%s",
                    self._queue_name,
                    self._message_log_context(msg),
                    exc,
                )
            finally:
                self._queue.task_done()

    async def _process_persisted_message(self, msg: MessageT) -> None:
        """处理持久任务并写入成功/失败状态。"""
        message_key = self._persistent_message_key(msg)
        try:
            await self._process_one(msg)
        except Exception as exc:
            await self._mark_persisted_failed(message_key, exc)
            logger.error(
                "%s 持久消息处理异常 %s err=%s",
                self._queue_name,
                self._message_log_context(msg),
                exc,
            )
        else:
            await self._mark_persisted_processed(message_key)

    async def _claim_persisted_message(self) -> MessageT | None:
        """从持久 inbox 认领任务；非持久队列默认无任务。"""
        return None

    async def _mark_persisted_processed(self, message_key: str) -> None:
        """标记持久任务成功；非持久队列无操作。"""

    async def _mark_persisted_failed(self, message_key: str, error: Exception) -> None:
        """标记持久任务失败；非持久队列无操作。"""

    def _persistent_message_key(self, msg: MessageT) -> str:
        """返回持久任务的唯一键。"""
        raise NotImplementedError

    @abstractmethod
    async def _process_one(self, msg: MessageT) -> None:
        """处理单条消息。"""

    @abstractmethod
    def _message_log_context(self, msg: MessageT) -> str:
        """返回异常日志中的消息上下文。"""
