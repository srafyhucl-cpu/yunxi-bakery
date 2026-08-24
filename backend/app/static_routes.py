"""根目录静态辅助路由。"""

from pathlib import Path

from fastapi.exceptions import HTTPException
from fastapi.responses import FileResponse

BASE_DIR = Path(__file__).resolve().parent


async def serve_verify_txt(filename: str, base_dir: Path = BASE_DIR) -> FileResponse:
    """微信/有赞等平台域名所有权 TXT 文件根目录穿透自动响应路由。"""
    safe_filename = Path(filename).name
    file_path = base_dir / "static" / f"{safe_filename}.txt"
    if file_path.exists():
        return FileResponse(str(file_path))
    raise HTTPException(status_code=404, detail="Not Found")


async def serve_favicon(base_dir: Path = BASE_DIR) -> FileResponse:
    """网站根目录 favicon.ico 图标响应。"""
    ico_path = base_dir.parent / "web" / "admin" / "dist" / "favicon.ico"
    if not ico_path.exists():
        ico_path = base_dir / "static" / "favicon.ico"
    if ico_path.exists():
        return FileResponse(str(ico_path))
    raise HTTPException(status_code=404, detail="Not Found")
