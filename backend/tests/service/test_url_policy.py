"""远程 URL SSRF 和响应边界合同测试。"""

import pytest

from app.service.security.url_policy import (
    UnsafeRemoteUrl,
    fetch_limited_remote_image,
    validate_remote_url,
)


class _StreamResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        chunks: tuple[bytes, ...] = (b"image",),
    ) -> None:
        self.status_code = status_code
        self.headers = headers or {"content-type": "image/jpeg"}
        self._chunks = chunks

    async def __aenter__(self) -> "_StreamResponse":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def aiter_bytes(self):
        for chunk in self._chunks:
            yield chunk


class _StreamClient:
    responses: list[_StreamResponse] = []
    requested_urls: list[str] = []

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "_StreamClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def stream(self, method: str, url: str) -> _StreamResponse:
        assert method == "GET"
        self.requested_urls.append(url)
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_url_policy_rejects_private_resolution(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.service.security.url_policy._resolve_addresses",
        lambda _hostname, _port: {"127.0.0.1"},
    )

    with pytest.raises(UnsafeRemoteUrl):
        await validate_remote_url("https://img.example/file.jpg", ["img.example"])


@pytest.mark.asyncio
async def test_url_policy_rejects_host_outside_allowlist(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.service.security.url_policy._resolve_addresses",
        lambda _hostname, _port: {"93.184.216.34"},
    )

    with pytest.raises(UnsafeRemoteUrl):
        await validate_remote_url("https://attacker.example/file.jpg", ["img.example"])


@pytest.mark.asyncio
async def test_fetch_revalidates_redirect_target(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.service.security.url_policy._resolve_addresses",
        lambda _hostname, _port: {"93.184.216.34"},
    )
    _StreamClient.requested_urls = []
    _StreamClient.responses = [
        _StreamResponse(status_code=302, headers={"location": "https://evil.test/x"})
    ]

    with pytest.raises(UnsafeRemoteUrl):
        await fetch_limited_remote_image(
            "https://img.example/start",
            allowed_hosts=["img.example"],
            timeout_seconds=1,
            max_bytes=10,
            client_factory=_StreamClient,
        )

    assert _StreamClient.requested_urls == ["https://img.example/start"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        _StreamResponse(headers={"content-type": "text/html"}),
        _StreamResponse(headers={"content-type": "image/jpeg", "content-length": "11"}),
        _StreamResponse(chunks=(b"123456", b"78901")),
    ],
)
async def test_fetch_rejects_mime_and_size_boundaries(monkeypatch, response) -> None:
    monkeypatch.setattr(
        "app.service.security.url_policy._resolve_addresses",
        lambda _hostname, _port: {"93.184.216.34"},
    )
    _StreamClient.responses = [response]

    result = await fetch_limited_remote_image(
        "https://img.example/file",
        allowed_hosts=["img.example"],
        timeout_seconds=1,
        max_bytes=10,
        client_factory=_StreamClient,
    )

    assert result is None
