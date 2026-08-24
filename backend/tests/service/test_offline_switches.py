"""离线 QA、知识缺口和 memory 独立开关合同测试。"""

import asyncio
from types import SimpleNamespace

import pytest

from app.service.offline import bootstrap


@pytest.mark.asyncio
async def test_offline_switches_can_enable_only_qa(monkeypatch) -> None:
    monkeypatch.setattr(bootstrap.settings, "ENABLE_OFFLINE_QA", True)
    monkeypatch.setattr(bootstrap.settings, "ENABLE_OFFLINE_KNOWLEDGE_GAP", False)
    monkeypatch.setattr(bootstrap.settings, "ENABLE_OFFLINE_MEMORY", False)

    class _Scheduler:
        instance = None

        def __init__(self, *, orchestrator, **_kwargs) -> None:
            self.orchestrator = orchestrator
            _Scheduler.instance = self

        def start(self) -> asyncio.Task[None]:
            return asyncio.create_task(asyncio.sleep(0))

    monkeypatch.setattr(bootstrap, "QaReviewAgent", lambda **_kwargs: object())
    monkeypatch.setattr(bootstrap, "KnowledgeGapAgent", lambda **_kwargs: object())
    monkeypatch.setattr(bootstrap, "MemoryAgent", lambda **_kwargs: object())
    monkeypatch.setattr(bootstrap, "OfflineReviewScheduler", _Scheduler)

    tasks: set[asyncio.Task[None]] = set()
    bootstrap.register_offline_review_scheduler(
        SimpleNamespace(state=SimpleNamespace()),
        repos={
            "session_repo": object(),
            "message_repo": object(),
            "conversation_review_repo": object(),
        },
        bg_tasks=tasks,
        scope_factory=lambda: None,
    )
    await asyncio.gather(*tasks)

    assert _Scheduler.instance is not None
    assert _Scheduler.instance.orchestrator._qa_review_agent is not None
    assert _Scheduler.instance.orchestrator._knowledge_gap_agent is None
    assert _Scheduler.instance.orchestrator._memory_agent is None
