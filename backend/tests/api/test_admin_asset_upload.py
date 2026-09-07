"""上传图片真实校验测试：合法样本与伪装损坏拒绝。"""

import struct

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.admin import assets as assets_module
from app.service.security.image_validation import (
    MAX_IMAGE_PIXELS,
    parse_image_dimensions,
    sniff_image_format,
    validate_decoration_image,
)


def _png_bytes(width: int, height: int) -> bytes:
    """构造最小 PNG 字节。"""
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + struct.pack(">I", 13)
        + b"IHDR"
        + ihdr
        + b"\x00\x00\x00\x00"
    )


def _jpeg_bytes(width: int, height: int) -> bytes:
    """构造最小 JPEG 字节。"""
    return (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
        b"\xff\xc0\x00\x08\x08" + struct.pack(">HH", height, width) + b"\x01\xff\xd9"
    )


def _webp_vp8x_bytes(width: int, height: int) -> bytes:
    """构造最小 VP8X 字节。"""
    dims = (width - 1).to_bytes(3, "big") + (height - 1).to_bytes(3, "big")
    return (
        b"RIFF"
        + struct.pack("<I", 22)
        + b"WEBP"
        + b"VP8X"
        + struct.pack("<I", 10)
        + b"\x00\x00\x00\x00"
        + dims
    )


def test_valid_png_accepted() -> None:
    """合法 PNG 通过并返回维度。"""
    content = _png_bytes(2, 3)
    assert sniff_image_format(content) == ".png"
    assert parse_image_dimensions(content, ".png") == (2, 3)
    assert validate_decoration_image(content, ".png") == (2, 3)


def test_valid_jpeg_accepted() -> None:
    """合法 JPEG 通过并返回维度。"""
    content = _jpeg_bytes(4, 5)
    assert sniff_image_format(content) == ".jpg"
    assert parse_image_dimensions(content, ".jpg") == (4, 5)
    assert validate_decoration_image(content, ".jpg") == (4, 5)


def test_valid_webp_accepted() -> None:
    """合法 WEBP 通过并返回维度。"""
    content = _webp_vp8x_bytes(6, 7)
    assert sniff_image_format(content) == ".webp"
    assert validate_decoration_image(content, ".webp") == (6, 7)


@pytest.mark.parametrize(
    "content",
    [
        b"",
        b"not an image at all",
        b"#!/bin/bash\necho hacked\n",
        b"\x89PNG\r\n\x1a\nshort",
        b"\xff\xd8\xff\xc0truncated",
        b"RIFF\x00\x00\x00\x00WEB",
    ],
)
def test_script_and_corrupt_files_rejected(content: bytes) -> None:
    """脚本与损坏文件一律拒绝。"""
    with pytest.raises(ValueError):
        validate_decoration_image(content, ".png")


def test_disguised_extension_rejected() -> None:
    """伪装扩展名拒绝，以真实魔数为准。"""
    with pytest.raises(ValueError, match="不一致"):
        validate_decoration_image(_png_bytes(1, 1), ".jpg")
    with pytest.raises(ValueError, match="不一致"):
        validate_decoration_image(_jpeg_bytes(1, 1), ".png")


def test_oversize_pixels_rejected() -> None:
    """超像素预算拒绝，不解压。"""
    side = int(MAX_IMAGE_PIXELS**0.5) + 1
    with pytest.raises(ValueError, match="像素"):
        validate_decoration_image(_png_bytes(side, side), ".png")


def test_upload_route_rejects_fake_image(tmp_path, monkeypatch) -> None:
    """上传接口拒绝伪装图片且不落盘。"""
    monkeypatch.setattr(assets_module, "STATIC_UPLOAD_DIR", tmp_path / "uploads")
    test_app = FastAPI()
    test_app.include_router(assets_module.create_admin_assets_router())
    test_app.dependency_overrides[assets_module.verify_token] = lambda: None
    client = TestClient(test_app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/admin/shop-config/assets",
        files={"file": ("evil.jpg", b"not an image", "image/jpeg")},
    )
    assert response.status_code == 400
    assert (
        list((tmp_path / "uploads").glob("*")) == []
        if (tmp_path / "uploads").exists()
        else True
    )


def test_upload_route_accepts_real_png(tmp_path, monkeypatch) -> None:
    """上传接口接受真实图片并落盘到隔离目录。"""
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(assets_module, "STATIC_UPLOAD_DIR", upload_dir)
    test_app = FastAPI()
    test_app.include_router(assets_module.create_admin_assets_router())
    test_app.dependency_overrides[assets_module.verify_token] = lambda: None
    client = TestClient(test_app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/admin/shop-config/assets",
        files={"file": ("cake.png", _png_bytes(2, 2), "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["data"]["imageUrl"].endswith(".png")
    assert len(list(upload_dir.glob("decoration-*.png"))) == 1


def test_upload_route_ignores_malicious_filename(tmp_path, monkeypatch) -> None:
    """恶意文件名不得影响落盘路径，存储键由服务端生成。"""
    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(assets_module, "STATIC_UPLOAD_DIR", upload_dir)
    test_app = FastAPI()
    test_app.include_router(assets_module.create_admin_assets_router())
    test_app.dependency_overrides[assets_module.verify_token] = lambda: None
    client = TestClient(test_app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/admin/shop-config/assets",
        files={"file": ("../../evil.png", _png_bytes(2, 2), "image/png")},
    )
    assert response.status_code == 200
    image_url = response.json()["data"]["imageUrl"]
    assert ".." not in image_url
    assert image_url.startswith("/static/uploads/decoration/decoration-")
    assert len(list(upload_dir.iterdir())) == 1
