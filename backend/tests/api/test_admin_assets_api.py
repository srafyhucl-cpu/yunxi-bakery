"""后台装修素材上传 API 测试。"""

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI

from app.api.admin_assets import create_admin_assets_router
from app.config import settings


@pytest.fixture
def app() -> FastAPI:
    """构建只包含后台素材上传路由的测试应用。"""
    test_app = FastAPI()
    test_app.include_router(create_admin_assets_router())
    return test_app


@pytest.mark.asyncio
async def test_admin_upload_decoration_asset_returns_static_url(app: FastAPI) -> None:
    """后台上传装修图片后返回小程序可访问的静态路径。"""
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    transport = httpx.ASGITransport(app=app)
    uploaded_path: Path | None = None

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/admin/shop-config/assets",
            files={"file": ("hero.png", b"\x89PNG\r\n\x1a\nhero", "image/png")},
            headers=headers,
        )

    assert response.status_code == 200
    image_url = response.json()["data"]["imageUrl"]
    assert image_url.startswith("/static/uploads/decoration/decoration-")
    uploaded_path = Path(__file__).resolve().parents[2] / "app" / image_url.lstrip("/")
    assert uploaded_path.exists()
    uploaded_path.unlink()


@pytest.mark.asyncio
async def test_admin_upload_decoration_asset_supports_multiple_images(
    app: FastAPI,
) -> None:
    """后台连续上传多张装修图片时应都返回可访问的静态路径。"""
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    transport = httpx.ASGITransport(app=app)
    uploaded_paths: list[Path] = []

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        first_response = await client.post(
            "/api/v1/admin/shop-config/assets",
            files={"file": ("hero-1.png", b"\x89PNG\r\n\x1a\nhero-1", "image/png")},
            headers=headers,
        )
        second_response = await client.post(
            "/api/v1/admin/shop-config/assets",
            files={"file": ("hero-2.webp", b"RIFFhero-2", "image/webp")},
            headers=headers,
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_url = first_response.json()["data"]["imageUrl"]
    second_url = second_response.json()["data"]["imageUrl"]
    assert first_url != second_url
    uploaded_paths.append(
        Path(__file__).resolve().parents[2] / "app" / first_url.lstrip("/")
    )
    uploaded_paths.append(
        Path(__file__).resolve().parents[2] / "app" / second_url.lstrip("/")
    )
    for uploaded_path in uploaded_paths:
        assert uploaded_path.exists()
        uploaded_path.unlink()


@pytest.mark.asyncio
async def test_admin_upload_decoration_asset_requires_token(app: FastAPI) -> None:
    """后台装修素材上传必须校验管理员 Token。"""
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/admin/shop-config/assets",
            files={"file": ("hero.png", b"image", "image/png")},
        )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_upload_decoration_asset_rejects_non_image(app: FastAPI) -> None:
    """后台装修素材上传拒绝非图片类型。"""
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.post(
            "/api/v1/admin/shop-config/assets",
            files={"file": ("hero.txt", b"text", "text/plain")},
            headers=headers,
        )

    assert response.status_code == 400
    assert "JPG" in response.json()["detail"]
