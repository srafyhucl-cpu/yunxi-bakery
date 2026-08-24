"""管理后台 AI 对话调试 API。"""

import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.admin import (
    ADMIN_SESSION_COOKIE,
    admin_login_is_allowed,
    clear_admin_login_failures,
    has_admin_api_access,
    is_allowed_admin_origin,
    is_valid_admin_session,
    is_valid_admin_token,
    issue_admin_session,
    record_admin_login_failure,
    set_admin_session_cookie,
    verify_token,
)
from app.config import settings
from app.logger import setup_logger
from app.service.admin import AdminService
from app.service.chat import ChatService
from app.service.cost_circuit_breaker import CostCircuitBreaker

logger = setup_logger()
AI_DIALOG_TIMEOUT_SECONDS = 35.0


def create_dialog_router(
    chat_service: ChatService,
    admin_service: AdminService,
) -> APIRouter:
    """工厂函数：返回 AI 对话调试相关 API 路由。"""
    router = APIRouter(prefix="/api/v1/admin", tags=["admin-dialog"])
    ai_cost_breaker = CostCircuitBreaker(
        settings.ADMIN_AI_FAILURE_THRESHOLD,
        settings.ADMIN_AI_COOLDOWN_SECONDS,
    )

    @router.get("/me")
    async def auth_me(
        request: Request,
        authorization: str | None = Header(default=None),
    ) -> JSONResponse:
        if not has_admin_api_access(request, authorization):
            raise HTTPException(status_code=401, detail="未登录或登录已过期")

        response = JSONResponse(
            {"ok": True, "data": {"name": "管理员", "role": "admin"}}
        )

        # 自愈机制：如果验证通过，提取合法 Token 并强制补发带有正确全局 path 的 Cookie，
        # 用于修复因用户浏览器残留旧的 /auth/ 局部路径 Cookie 而导致后续业务接口 401 的无限重定向死循环
        session_token = request.cookies.get(ADMIN_SESSION_COOKIE)
        if not is_valid_admin_session(session_token):
            if not (
                settings.ADMIN_ALLOW_LEGACY_BEARER
                and authorization
                and authorization.startswith("Bearer ")
                and is_valid_admin_token(authorization.removeprefix("Bearer "))
            ):
                raise HTTPException(status_code=401, detail="未登录或登录已过期")
            session_token = issue_admin_session()
            set_admin_session_cookie(response, session_token)

        return response

    @router.post("/auth/login")
    async def auth_login(request: Request) -> JSONResponse:
        if not is_allowed_admin_origin(request):
            raise HTTPException(status_code=403, detail="请求来源不受信任")
        if not admin_login_is_allowed(request):
            raise HTTPException(status_code=429, detail="登录尝试过于频繁")
        body = await request.json()
        token = str(body.get("token", "")).strip()
        if not is_valid_admin_token(token):
            record_admin_login_failure(request)
            raise HTTPException(status_code=401, detail="Token 无效")
        clear_admin_login_failures(request)
        response = JSONResponse(
            {
                "ok": True,
                "message": "登录成功",
                "data": {"name": "管理员", "role": "admin"},
            },
        )
        set_admin_session_cookie(response, issue_admin_session())
        return response

    @router.post("/auth/logout")
    async def auth_logout() -> JSONResponse:
        response = JSONResponse({"ok": True, "message": "已退出登录"})
        response.delete_cookie(ADMIN_SESSION_COOKIE, path="/")
        response.delete_cookie("admin_token", path="/")
        return response

    @router.get("/ai-dialog/sessions", dependencies=[Depends(verify_token)])
    async def list_ai_dialog_sessions() -> dict:
        """获取所有 AI 对话列表（含置顶状态），置顶优先、再按更新时间降序。"""
        sessions = await admin_service.get_all_by_channel(channel="admin_test")
        items = []
        for s in sessions:
            extra = json.loads(s.extra_info or "{}")
            items.append(
                {
                    "id": s.id,
                    "name": extra.get("name", ""),
                    "user_id": s.user_id,
                    "pinned": bool(extra.get("pinned", False)),
                    "user_display": extra.get("user_display", ""),
                    "last_msg": extra.get("last_msg", ""),
                    "created_at": s.created_at,
                    "updated_at": s.updated_at,
                }
            )
        items.sort(key=lambda x: (x["pinned"], x["updated_at"]), reverse=True)
        return {"code": 0, "data": items}

    @router.post("/ai-dialog/save", dependencies=[Depends(verify_token)])
    async def save_ai_dialog(request: Request) -> dict:
        """命名并保存 AI 对话（新建对话后首条消息自动调用）。"""
        body = json.loads((await request.body()).decode("utf-8"))
        session_id = body.get("session_id", "")
        name = body.get("name", "").strip()
        user_display = body.get("user_display", "").strip()
        if not session_id or not name:
            return {"code": 422, "message": "参数不完整"}
        session = await admin_service.get(session_id)
        if not session:
            return {"code": 404, "message": "会话不存在"}
        extra = json.loads(session.extra_info or "{}")
        extra["name"] = name
        if user_display:
            extra["user_display"] = user_display
        await admin_service.update_extra(
            session_id, json.dumps(extra, ensure_ascii=False)
        )
        return {"code": 0, "message": "已保存"}

    @router.post(
        "/ai-dialog/session/{session_id}/pin", dependencies=[Depends(verify_token)]
    )
    async def pin_ai_dialog_session(session_id: str) -> dict:
        """切换 AI 对话置顶状态。"""
        session = await admin_service.get(session_id)
        if not session:
            return {"code": 404, "message": "会话不存在"}
        extra = json.loads(session.extra_info or "{}")
        extra["pinned"] = not bool(extra.get("pinned", False))
        await admin_service.update_extra(
            session_id, json.dumps(extra, ensure_ascii=False)
        )
        return {"code": 0, "pinned": extra["pinned"]}

    @router.delete(
        "/ai-dialog/session/{session_id}", dependencies=[Depends(verify_token)]
    )
    async def delete_ai_dialog_session(session_id: str) -> dict:
        """删除一条 AI 对话记录。"""
        session = await admin_service.get(session_id)
        if not session:
            return {"code": 404, "message": "会话不存在"}
        await admin_service.update_status(session_id, "closed")
        return {"code": 0, "message": "已丢弃"}

    @router.get("/ai-dialog/messages", dependencies=[Depends(verify_token)])
    async def ai_dialog_history(user_id: str = "admin_tester") -> dict:
        """获取 AI 对话的历史消息（按 user_id 查最近活跃会话）。"""
        session = await admin_service.get_active(user_id, "admin_test")
        if not session:
            return {"code": 0, "data": []}
        msgs = await admin_service.get_by_session(session.id)
        return {
            "code": 0,
            "session_id": session.id,
            "data": [
                {
                    "role": m.role.value if hasattr(m.role, "value") else m.role,
                    "content": m.content,
                    "created_at": m.created_at,
                }
                for m in msgs
            ],
        }

    @router.post("/ai-dialog", dependencies=[Depends(verify_token)])
    async def ai_dialog_api(request: Request) -> dict:
        raw = await request.body()
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("gbk")
        body = json.loads(text)
        content = body.get("content", "").strip()
        if not content:
            return {"code": 422, "message": "内容不能为空"}
        from app.service.llm.intent import detect_intent

        intent = await detect_intent(content)
        test_user = body.get("user_id", "admin_tester")
        s = await admin_service.get_active(test_user, "admin_test")
        if s and s.status in ("transfer_pending", "human_service"):
            await admin_service.update_status(s.id, "active")
        if not ai_cost_breaker.allow():
            raise HTTPException(status_code=503, detail="AI 服务暂时熔断，请稍后重试")
        try:
            reply = await asyncio.wait_for(
                chat_service.handle_message(
                    channel="admin_test",
                    user_id=test_user,
                    channel_msg_id=str(uuid.uuid4()),
                    content=content,
                ),
                timeout=AI_DIALOG_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            ai_cost_breaker.record_failure()
            logger.error(
                "后台 AI 对话接口超时: user=%s content=%s", test_user, content[:80]
            )
            return {
                "code": 0,
                "reply": "查询超时了，当前大模型服务响应较慢。请稍后重试，或直接联系人工确认订单配送时间。",
                "intent": intent,
                "session_id": s.id if s else "",
            }
        except Exception:
            ai_cost_breaker.record_failure()
            raise
        ai_cost_breaker.record_success()
        session = await admin_service.get_active(test_user, "admin_test")
        session_id = session.id if session else ""
        clean = (reply or "(无回复)").replace("**", "").replace("*", "")
        if session_id:
            s2 = await admin_service.get(session_id)
            if s2:
                extra2 = json.loads(s2.extra_info or "{}")
                if extra2.get("name"):
                    extra2["last_msg"] = clean[:60]
                    await admin_service.update_extra(
                        session_id, json.dumps(extra2, ensure_ascii=False)
                    )
        return {"code": 0, "reply": clean, "intent": intent, "session_id": session_id}

    return router
