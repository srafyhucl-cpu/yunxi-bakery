"""运行时 readiness HTTP 状态码合同测试。"""

import httpx
import pytest
from fastapi import FastAPI

from app.api.runtime import build_ready_payload


@pytest.mark.asyncio
async def test_ready_payload_sets_503_when_checks_fail() -> None:
    app = FastAPI()
    app.state.offline_review_scheduler = None

    response = httpx.Response(200)
    payload = build_ready_payload(
        app,
        checks_builder=lambda: {"database": False},
        feature_builder=lambda _running: {},
        response=response,
    )

    assert payload["status"] == "degraded"
    assert response.status_code == 503


def test_ready_payload_uses_startup_readiness_snapshot() -> None:
    app = FastAPI()
    app.state.readiness_checks = {"database": True}

    def unexpected_live_check() -> dict[str, bool]:
        raise AssertionError("ready should use the startup snapshot")

    payload = build_ready_payload(
        app,
        checks_builder=unexpected_live_check,
        feature_builder=lambda _running: {},
    )

    assert payload["status"] == "ready"
    assert payload["checks"] == {"database": True}


def test_ready_payload_falls_back_before_startup_snapshot() -> None:
    app = FastAPI()

    payload = build_ready_payload(
        app,
        checks_builder=lambda: {"database": False},
        feature_builder=lambda _running: {},
    )

    assert payload["status"] == "degraded"
