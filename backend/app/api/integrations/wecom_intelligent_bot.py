"""企微智能机器人入口。"""

import secrets
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import APIRouter, Body, Header, HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

from app.config import settings
from app.logger import setup_logger
from app.service.wecom.intelligent_bot_callback import (
    WeComBotCallbackConfig,
    WeComBotCallbackError,
    WeComBotCallbackService,
)
from app.service.wecom.employee_agent_service import EmployeeAgentService
from app.service.wecom.intelligent_bot_dispatcher import WeComBotMessageDispatcher
from app.service.wecom.intelligent_bot_ops_tools import WeComBotOpsToolService
from app.service.wecom.intelligent_bot_plugin import WeComBotPluginService
from app.service.wecom.intelligent_bot_status_tools import WeComBotStatusToolService
from app.service.wecom.intelligent_bot_tools import WeComBotBusinessToolService
from app.service.wecom.employee_authorization import EmployeeActorAuthorizer

ToolHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]
logger = setup_logger()


def create_wecom_intelligent_bot_router(
    service: WeComBotPluginService | None = None,
    tool_service: WeComBotBusinessToolService | None = None,
    ops_tool_service: WeComBotOpsToolService | None = None,
    status_tool_service: WeComBotStatusToolService | None = None,
    agent_service: EmployeeAgentService | None = None,
    callback_service: WeComBotCallbackService | None = None,
) -> APIRouter:
    """创建企微智能机器人路由。"""
    router = APIRouter(
        prefix="/api/v1/wecom/intelligent-bot",
        tags=["wecom-intelligent-bot"],
    )
    plugin_service = service or WeComBotPluginService()
    business_tool_service = tool_service or WeComBotBusinessToolService()
    operations_tool_service = ops_tool_service or WeComBotOpsToolService()
    status_service = status_tool_service or WeComBotStatusToolService()
    callback_handler = callback_service or _build_callback_service(
        business_tool_service,
        operations_tool_service,
        status_service,
        agent_service,
    )
    _register_callback_routes(router, callback_handler)
    _register_ping_routes(router, plugin_service)
    _register_tool_routes(router, business_tool_service)
    _register_ops_tool_routes(router, operations_tool_service)
    _register_status_tool_routes(router, status_service)
    return router


def _build_callback_service(
    business_tool_service: WeComBotBusinessToolService,
    operations_tool_service: WeComBotOpsToolService,
    status_service: WeComBotStatusToolService,
    agent_service: EmployeeAgentService | None,
) -> WeComBotCallbackService:
    return WeComBotCallbackService(
        config=_build_callback_config(),
        dispatcher=WeComBotMessageDispatcher(
            business_tool_service=business_tool_service,
            ops_tool_service=operations_tool_service,
            status_tool_service=status_service,
            employee_agent_service=agent_service,
            actor_authorizer=EmployeeActorAuthorizer(),
        ),
    )


def _build_callback_config() -> WeComBotCallbackConfig:
    return WeComBotCallbackConfig(
        token=(
            settings.WECOM_INTELLIGENT_BOT_TOKEN.strip() or settings.WECOM_TOKEN.strip()
        ),
        encoding_aes_key=(
            settings.WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY.strip()
            or settings.WECOM_ENCODING_AES_KEY.strip()
        ),
    )


def _register_callback_routes(
    router: APIRouter,
    callback_service: WeComBotCallbackService,
) -> None:
    @router.get("/callback")
    async def verify_callback_url(
        msg_signature: str,
        timestamp: str,
        nonce: str,
        echostr: str,
    ) -> PlainTextResponse:
        if not callback_service.is_ready:
            return PlainTextResponse("配置未就绪", status_code=503)
        try:
            plaintext = callback_service.verify_url(
                msg_signature=msg_signature,
                timestamp=timestamp,
                nonce=nonce,
                echostr=echostr,
            )
        except WeComBotCallbackError as exc:
            logger.warning("企微智能机器人 URL 验证失败: %s", exc)
            return PlainTextResponse(str(exc), status_code=403)
        except Exception as exc:
            logger.error("企微智能机器人 URL 验证异常: %s", exc)
            return PlainTextResponse("解密失败", status_code=500)
        return PlainTextResponse(plaintext)

    @router.post("/callback")
    async def receive_callback(request: Request) -> Response:
        if not callback_service.is_ready:
            return PlainTextResponse("配置未就绪", status_code=503)
        query = request.query_params
        try:
            payload = await request.json()
        except ValueError:
            return PlainTextResponse("JSON 解析失败", status_code=400)
        if not isinstance(payload, dict):
            return PlainTextResponse("JSON 解析失败", status_code=400)
        try:
            reply = await callback_service.handle_callback(
                encrypted_payload=payload,
                msg_signature=query.get("msg_signature", ""),
                timestamp=query.get("timestamp", ""),
                nonce=query.get("nonce", ""),
            )
        except WeComBotCallbackError as exc:
            logger.warning("企微智能机器人回调拒绝: %s", exc)
            return PlainTextResponse(str(exc), status_code=403)
        if reply is None:
            return PlainTextResponse("")
        return JSONResponse(reply.to_dict())


def _register_ping_routes(
    router: APIRouter,
    plugin_service: WeComBotPluginService,
) -> None:
    @router.get("/plugins/ping")
    async def ping_get(
        authorization: str | None = Header(default=None),
        x_yunxi_bot_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _verify_plugin_key(authorization, x_yunxi_bot_key)
        return plugin_service.build_ping_response({})

    @router.post("/plugins/ping")
    async def ping_post(
        payload: dict[str, Any] | None = Body(default=None),
        authorization: str | None = Header(default=None),
        x_yunxi_bot_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _verify_plugin_key(authorization, x_yunxi_bot_key)
        return plugin_service.build_ping_response(payload or {})


def _register_tool_routes(
    router: APIRouter,
    business_tool_service: WeComBotBusinessToolService,
) -> None:
    _register_tool_endpoint(
        router, "/tools/order-lookup", business_tool_service.lookup_orders
    )
    _register_tool_endpoint(
        router, "/tools/product-lookup", business_tool_service.lookup_products
    )
    _register_tool_endpoint(
        router, "/tools/knowledge-answer", business_tool_service.answer_knowledge
    )


def _register_ops_tool_routes(
    router: APIRouter,
    operations_tool_service: WeComBotOpsToolService,
) -> None:
    _register_tool_endpoint(
        router, "/tools/customer-lookup", operations_tool_service.lookup_customer
    )
    _register_tool_endpoint(
        router,
        "/tools/group-campaign-summary",
        operations_tool_service.summarize_group_campaign,
    )
    _register_tool_endpoint(
        router,
        "/tools/handoff-pending",
        operations_tool_service.list_pending_handoffs,
    )


def _register_status_tool_routes(
    router: APIRouter,
    status_tool_service: WeComBotStatusToolService,
) -> None:
    _register_tool_endpoint(
        router, "/tools/ops-summary", status_tool_service.summarize_ops
    )
    _register_tool_endpoint(
        router,
        "/tools/integration-status",
        status_tool_service.summarize_integrations,
    )
    _register_tool_endpoint(
        router,
        "/tools/offline-review-summary",
        status_tool_service.summarize_offline_review,
    )


def _register_tool_endpoint(
    router: APIRouter,
    path: str,
    handler: ToolHandler,
) -> None:
    @router.post(path)
    async def tool_endpoint(
        payload: dict[str, Any] | None = Body(default=None),
        authorization: str | None = Header(default=None),
        x_yunxi_bot_key: str | None = Header(default=None),
    ) -> dict[str, Any]:
        _verify_plugin_key(authorization, x_yunxi_bot_key)
        return await handler(payload or {})


def _verify_plugin_key(
    authorization: str | None,
    x_yunxi_bot_key: str | None,
) -> None:
    configured_key = settings.WECOM_BOT_PLUGIN_API_KEY.strip()
    if not configured_key:
        raise HTTPException(status_code=503, detail="企微机器人插件密钥未配置")
    provided_key = _extract_plugin_key(authorization, x_yunxi_bot_key)
    if not secrets.compare_digest(provided_key, configured_key):
        raise HTTPException(status_code=401, detail="企微机器人插件密钥无效")


def _extract_plugin_key(
    authorization: str | None,
    x_yunxi_bot_key: str | None,
) -> str:
    if x_yunxi_bot_key:
        return x_yunxi_bot_key.strip()
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            return token.strip()
    return ""
