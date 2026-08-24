"""后台装修素材上传 API。"""

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.admin import verify_token

MAX_DECORATION_ASSET_BYTES = 2 * 1024 * 1024
ALLOWED_DECORATION_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
STATIC_UPLOAD_DIR = (
    Path(__file__).resolve().parents[2] / "static" / "uploads" / "decoration"
)


def create_admin_assets_router() -> APIRouter:
    """创建后台装修素材上传路由。"""
    router = APIRouter(
        prefix="/api/v1/admin/shop-config/assets",
        tags=["admin-assets"],
        dependencies=[Depends(verify_token)],
    )

    @router.post("")
    async def upload_decoration_asset(file: UploadFile = File(...)) -> dict:
        """上传装修图片素材并返回小程序可访问路径。"""
        suffix = ALLOWED_DECORATION_IMAGE_TYPES.get(file.content_type or "")
        if not suffix:
            raise HTTPException(status_code=400, detail="仅支持 JPG、PNG、WEBP 图片")

        content = await file.read(MAX_DECORATION_ASSET_BYTES + 1)
        if not content:
            raise HTTPException(status_code=400, detail="图片文件不能为空")
        if len(content) > MAX_DECORATION_ASSET_BYTES:
            raise HTTPException(status_code=400, detail="图片不能超过 2MB")

        STATIC_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"decoration-{uuid4().hex}{suffix}"
        file_path = STATIC_UPLOAD_DIR / filename
        file_path.write_bytes(content)
        image_url = f"/static/uploads/decoration/{filename}"
        return {"code": 0, "data": {"imageUrl": image_url}}

    return router
