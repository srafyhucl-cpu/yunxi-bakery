"""高成本外部调用的轻量熔断状态机。"""

import time


class CostCircuitBreaker:
    """按连续失败次数限制高成本调用，避免上游故障持续消耗额度。"""

    def __init__(self, failure_threshold: int, cooldown_seconds: float) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = cooldown_seconds
        self._failure_count = 0
        self._opened_at = 0.0
        self._probe_in_flight = False

    @property
    def is_open(self) -> bool:
        """返回当前是否处于熔断状态。"""
        return self._opened_at > 0

    def allow(self) -> bool:
        """判断是否允许本次调用。"""
        if not self.is_open:
            return True
        if time.monotonic() - self._opened_at < self._cooldown_seconds:
            return False
        if self._probe_in_flight:
            return False
        self._probe_in_flight = True
        return True

    def record_success(self) -> None:
        """成功后关闭熔断并清理失败计数。"""
        self._failure_count = 0
        self._opened_at = 0.0
        self._probe_in_flight = False

    def record_failure(self) -> None:
        """失败后累计计数，达到阈值时打开熔断。"""
        self._probe_in_flight = False
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold:
            self._opened_at = time.monotonic()


__all__ = ["CostCircuitBreaker"]
