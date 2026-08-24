"""高成本调用熔断器测试。"""

import time

from app.service.cost_circuit_breaker import CostCircuitBreaker


def test_breaker_opens_after_failures_and_recovers_with_probe(
    monkeypatch,
) -> None:
    """连续失败应打开熔断，冷却后只放行一个探针并在成功后恢复。"""
    current_time = 100.0
    monkeypatch.setattr(time, "monotonic", lambda: current_time)
    breaker = CostCircuitBreaker(failure_threshold=2, cooldown_seconds=10)

    assert breaker.allow() is True
    breaker.record_failure()
    assert breaker.allow() is True
    breaker.record_failure()
    assert breaker.is_open is True
    assert breaker.allow() is False

    current_time = 111.0
    assert breaker.allow() is True
    assert breaker.allow() is False
    breaker.record_success()
    assert breaker.is_open is False
    assert breaker.allow() is True
