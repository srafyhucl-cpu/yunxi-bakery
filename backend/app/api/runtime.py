"""运行时健康与就绪状态读模型。"""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, Response

from app.config import APP_VERSION
from app.readiness import build_readiness_checks, build_runtime_feature_flags


def build_ready_payload(
    app: FastAPI,
    checks_builder: Callable[[], dict[str, bool]] = build_readiness_checks,
    feature_builder: Callable[[bool], dict[str, Any]] = build_runtime_feature_flags,
    response: Response | None = None,
) -> dict[str, Any]:
    """构建就绪检查响应，隔离运行时读模型职责。"""
    cached_checks = getattr(app.state, "readiness_checks", None)
    checks = (
        dict(cached_checks) if isinstance(cached_checks, dict) else checks_builder()
    )
    offline_review_scheduler = getattr(app.state, "offline_review_scheduler", None)
    offline_review_summary = (
        offline_review_scheduler.get_last_summary()
        if offline_review_scheduler is not None
        else None
    )
    payload = {
        "status": "ready" if all(checks.values()) else "degraded",
        "version": APP_VERSION,
        "checks": checks,
        "features": feature_builder(
            bool(offline_review_summary and offline_review_summary.ran)
        ),
    }
    if response is not None and payload["status"] != "ready":
        response.status_code = 503
    return payload


__all__ = ["build_ready_payload"]
