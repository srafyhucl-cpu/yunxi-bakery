"""生产运行时版本门禁测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from scripts import check_langchain_production_runtime_version as checker


@pytest.mark.asyncio
async def test_runtime_version_passes_when_health_and_ready_match(monkeypatch) -> None:
    monkeypatch.setattr(checker.httpx, "AsyncClient", fake_client_factory("0.99.0"))

    report = await checker.build_runtime_version_report(
        base_url="https://example.com/",
        expected_version="0.99.0",
    )

    assert report["status"] == "passed"
    assert report["endpoint_versions"] == {"health": "0.99.0", "ready": "0.99.0"}
    assert report["failed"] == 0


@pytest.mark.asyncio
async def test_runtime_version_fails_when_endpoint_versions_are_old(
    monkeypatch,
) -> None:
    monkeypatch.setattr(checker.httpx, "AsyncClient", fake_client_factory("0.85.2"))

    report = await checker.build_runtime_version_report(
        base_url="https://example.com",
        expected_version="0.99.0",
    )

    assert report["status"] == "failed"
    assert report["failed"] == 2
    assert report["failed_names"] == ["health", "ready"]
    assert report["endpoint_versions"] == {"health": "0.85.2", "ready": "0.85.2"}


@pytest.mark.asyncio
async def test_runtime_version_records_request_failure(monkeypatch) -> None:
    monkeypatch.setattr(checker.httpx, "AsyncClient", failing_client_factory())

    report = await checker.build_runtime_version_report(
        base_url="https://example.com",
        expected_version="0.99.0",
    )

    assert report["status"] == "failed"
    assert report["failed"] == 2
    assert report["results"][0]["status"] == "request_failed"
    assert report["endpoint_versions"] == {}


def test_main_writes_json_and_summary(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(checker.httpx, "AsyncClient", fake_client_factory("0.99.0"))
    output_path = tmp_path / "runtime.json"

    exit_code = asyncio_run(
        checker.main_async(
            [
                "--base-url",
                "https://example.com",
                "--expected-version",
                "0.99.0",
                "--json-out",
                str(output_path),
                "--summary",
            ]
        )
    )

    assert exit_code == 0
    assert output_path.exists()
    assert "langchain_production_runtime_version status=passed" in (
        capsys.readouterr().out
    )


def fake_client_factory(version: str):
    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url: str):
            status = "ready" if url.endswith("/ready") else "ok"
            return SimpleNamespace(
                raise_for_status=lambda: None,
                json=lambda: {"status": status, "version": version},
            )

    return FakeAsyncClient


def failing_client_factory():
    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url: str):
            raise httpx.ConnectError("connection failed")

    return FakeAsyncClient


def asyncio_run(coro):
    import asyncio

    return asyncio.run(coro)
