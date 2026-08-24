from dataclasses import dataclass

import pytest

from app.service.wecom.base_queue import BaseWeComMessageQueue


@dataclass(frozen=True)
class DummyMessage:
    message_id: str
    should_fail: bool = False


class DummyQueue(BaseWeComMessageQueue[DummyMessage]):
    def __init__(self) -> None:
        super().__init__(queue_max_size=10, queue_name="测试队列")
        self.processed: list[str] = []

    async def enqueue(self, msg: DummyMessage) -> bool:
        self._queue.put_nowait(msg)
        return True

    async def _process_one(self, msg: DummyMessage) -> None:
        if msg.should_fail:
            raise RuntimeError("模拟失败")
        self.processed.append(msg.message_id)

    def _message_log_context(self, msg: DummyMessage) -> str:
        return f"msg_id={msg.message_id}"


@pytest.mark.asyncio
async def test_worker_processes_messages_and_updates_queue_size() -> None:
    queue = DummyQueue()

    assert queue.queue_size == 0
    await queue.enqueue(DummyMessage("msg-1"))
    assert queue.queue_size == 1

    queue.start_worker(chat_service=object())
    await queue._queue.join()
    await queue.stop()

    assert queue.processed == ["msg-1"]
    assert queue.queue_size == 0


@pytest.mark.asyncio
async def test_worker_keeps_running_after_single_message_error() -> None:
    queue = DummyQueue()

    await queue.enqueue(DummyMessage("bad", should_fail=True))
    await queue.enqueue(DummyMessage("good"))

    queue.start_worker(chat_service=object())
    await queue._queue.join()
    await queue.stop()

    assert queue.processed == ["good"]
