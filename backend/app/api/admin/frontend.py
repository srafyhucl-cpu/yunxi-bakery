"""
新后台前端入口路由。

职责：
- 提供 `/admin-v2` 的静态资源访问
- 为 SPA 路由刷新提供 fallback
- 在前端尚未构建时返回明确提示
- 在向量数据库尚未加载完成时拦截路由，返回可视化进度条页面
"""

from pathlib import Path
from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, HTMLResponse

from app.api.admin import verify_token

BASE_DIR = Path(__file__).resolve().parents[3]
FRONTEND_DIST_DIR = BASE_DIR / "web" / "admin" / "dist"
FRONTEND_INDEX_FILE = FRONTEND_DIST_DIR / "index.html"
INDEX_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
}


def get_transition_html() -> str:
    """返回精美的、无外部依赖的向量自愈重构可视化进度静态过渡页面。"""
    html_path = BASE_DIR / "app" / "static" / "init_landing.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return "<h1>系统初始化中...</h1>"


def create_admin_frontend_router() -> APIRouter:
    router = APIRouter(tags=["admin-frontend"])

    @router.get("/api/admin/vector-build-status", dependencies=[Depends(verify_token)])
    async def get_vector_status(request: Request):
        vs = getattr(request.app.state, "vs", None)
        if not vs:
            return {
                "code": 200,
                "data": {
                    "status": "ready",
                    "percent": 100,
                    "total": 0,
                    "current": 0,
                    "elapsed": 0.0,
                    "last_build_duration": 0.0,
                    "detail": "向量服务未载入",
                },
            }

        progress_data = vs._init_progress
        status = progress_data["status"]
        total = progress_data["total"]
        current = progress_data["current"]
        elapsed = progress_data["elapsed"]
        last_duration = progress_data["last_build_duration"]

        percent = 0
        if status == "ready":
            percent = 100
        elif status == "building" and total > 0:
            percent = int((current / total) * 100)

        detail_msg = "向量数据库初始化中..."
        if status == "loading":
            detail_msg = "正在载入本地预解算缓存..."
        elif status == "building":
            detail_msg = f"AI正在后台积极学习知识库...({current} / {total})"
        elif status == "ready":
            detail_msg = "系统向量库初始化完成"
        elif status == "failed":
            detail_msg = "向量库初始化失败，请重试或查看日志"

        return {
            "code": 200,
            "data": {
                "status": status,
                "total": total,
                "current": current,
                "percent": percent,
                "elapsed": round(elapsed, 1),
                "last_build_duration": round(last_duration, 1),
                "detail": detail_msg,
            },
            "msg": "获取向量状态成功",
        }

    @router.post("/api/admin/vector-build-retry", dependencies=[Depends(verify_token)])
    async def retry_vector_build(request: Request):
        vs = getattr(request.app.state, "vs", None)
        if not vs:
            return {"code": 400, "message": "未找到向量服务"}

        if vs._init_progress["status"] in ["failed", "ready"]:
            import asyncio
            from app.config import settings

            vs_path = settings.EMBEDDING_INDEX_DIR
            asyncio.create_task(vs.rebuild_from_db(vs_path))
            return {"code": 200, "message": "重构任务已异步调起"}
        return {"code": 400, "message": "当前状态无需重试"}

    @router.get("/admin", response_class=HTMLResponse)
    @router.get("/admin/{asset_path:path}", response_class=HTMLResponse)
    async def admin_entry(request: Request = None, asset_path: str = ""):
        # 如果未构建，返回静态提示
        if not FRONTEND_INDEX_FILE.exists():
            return HTMLResponse(
                content=(
                    "<h1>admin 尚未构建</h1>"
                    "<p>请先在 web/admin 下执行 npm install 与 npm run build，"
                    "或直接启动 Vite 开发服务。</p>"
                ),
                status_code=503,
                headers=INDEX_CACHE_HEADERS,
            )

        # 核心拦截：如果向量库未初始化就绪，返回精美进度页面而不是 502
        if request:
            vs = getattr(request.app.state, "vs", None)
            if vs and vs._init_progress["status"] in [
                "uninitialized",
                "loading",
                "building",
                "failed",
            ]:
                return HTMLResponse(
                    content=get_transition_html(), headers=INDEX_CACHE_HEADERS
                )

        requested_path = (FRONTEND_DIST_DIR / asset_path).resolve()
        if asset_path:
            try:
                requested_path.relative_to(FRONTEND_DIST_DIR.resolve())
            except ValueError:
                return HTMLResponse(content="非法路径", status_code=400)

            if requested_path.exists() and requested_path.is_file():
                return FileResponse(str(requested_path))

        return FileResponse(str(FRONTEND_INDEX_FILE), headers=INDEX_CACHE_HEADERS)

    return router
