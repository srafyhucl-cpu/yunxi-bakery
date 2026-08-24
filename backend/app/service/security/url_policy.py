"""远程 URL allowlist、DNS 和响应大小安全策略。"""

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from collections.abc import Callable
from urllib.parse import urljoin, urlparse

import httpx

ALLOWED_SCHEMES = frozenset({"http", "https"})
MAX_REDIRECTS = 3


class UnsafeRemoteUrl(ValueError):
    """远程 URL 不满足出站安全策略。"""


async def validate_remote_url(url: str, allowed_hosts: Iterable[str]) -> None:
    """验证协议、主机 allowlist 和 DNS 解析后的地址。"""
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower().rstrip(".")
    hosts = {host.strip().lower().rstrip(".") for host in allowed_hosts if host.strip()}
    if parsed.scheme not in ALLOWED_SCHEMES or not hostname:
        raise UnsafeRemoteUrl("远程 URL 协议或主机无效")
    if hostname not in hosts and not any(
        hostname.endswith("." + host) for host in hosts
    ):
        raise UnsafeRemoteUrl("远程 URL 主机不在 allowlist")
    try:
        addresses = await asyncio.to_thread(_resolve_addresses, hostname, parsed.port)
    except OSError as exc:
        raise UnsafeRemoteUrl("远程 URL 主机无法解析") from exc
    if not addresses or any(_is_private_address(address) for address in addresses):
        raise UnsafeRemoteUrl("远程 URL 解析到受保护地址")


def _resolve_addresses(hostname: str, port: int | None) -> set[str]:
    resolved_port = port or 443
    return {
        str(result[4][0])
        for result in socket.getaddrinfo(
            hostname, resolved_port, type=socket.SOCK_STREAM
        )
    }


def _is_private_address(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


async def fetch_limited_remote_image(
    url: str,
    *,
    allowed_hosts: Iterable[str],
    timeout_seconds: float,
    max_bytes: int,
    client_factory: Callable[..., httpx.AsyncClient] = httpx.AsyncClient,
) -> tuple[bytes, str] | None:
    """逐跳验证重定向并流式读取有大小上限的图片。"""
    current_url = url
    async with client_factory(
        timeout=timeout_seconds, follow_redirects=False
    ) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await validate_remote_url(current_url, allowed_hosts)
            try:
                async with client.stream("GET", current_url) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = str(response.headers.get("location") or "")
                        if not location:
                            return None
                        current_url = urljoin(current_url, location)
                        continue
                    if response.status_code != 200:
                        return None
                    content_type = (
                        response.headers.get("content-type", "")
                        .split(";", 1)[0]
                        .strip()
                        .lower()
                    )
                    if not content_type.startswith("image/"):
                        return None
                    content_length = response.headers.get("content-length", "")
                    if content_length.isdigit() and int(content_length) > max_bytes:
                        return None
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > max_bytes:
                            return None
                    return bytes(content), content_type
            except httpx.HTTPError:
                return None
    return None
