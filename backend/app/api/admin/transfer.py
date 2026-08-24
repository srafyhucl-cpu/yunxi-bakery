"""管理后台转人工与会话消息 API。"""

from fastapi import APIRouter, Depends, HTTPException

from app.api.admin import verify_token
from app.service.admin import AdminService
from app.service.chat import ChatService
from app.service.transfer_manager import TransferManager


def create_transfer_router(
    transfer_mgr: TransferManager,
    admin_service: AdminService,
    chat_service: ChatService,
) -> APIRouter:
    """工厂函数：返回转人工与会话消息相关 API 路由。"""
    router = APIRouter(prefix="/api/v1/admin", tags=["admin-transfer"])

    @router.get("/transfers/pending", dependencies=[Depends(verify_token)])
    async def list_pending_transfers() -> dict:
        transfers = await transfer_mgr.get_pending()
        return {
            "code": 0,
            "data": [
                {
                    "id": t.id,
                    "session_id": t.session_id,
                    "user_id": t.user_id,
                    "reason": t.reason,
                    "conversation_summary": t.conversation_summary,
                    "created_at": t.created_at,
                }
                for t in transfers
            ],
        }

    @router.post(
        "/transfers/{transfer_id}/accept", dependencies=[Depends(verify_token)]
    )
    async def accept_transfer(transfer_id: str, staff_id: str = "") -> dict:
        await transfer_mgr.accept_transfer(transfer_id, staff_id)
        return {"code": 0, "message": "已接单"}

    @router.post("/transfers/{transfer_id}/close", dependencies=[Depends(verify_token)])
    async def close_transfer(transfer_id: str) -> dict:
        await transfer_mgr.close_transfer(transfer_id)
        return {"code": 0, "message": "已关闭"}

    @router.post("/sessions/{session_id}/reply", dependencies=[Depends(verify_token)])
    async def human_reply(session_id: str, content: str) -> dict:
        if not content.strip():
            raise HTTPException(status_code=422, detail="回复内容不能为空")
        await chat_service.handle_human_reply(session_id, content)
        return {"code": 0, "message": "已发送"}

    @router.get("/sessions/{session_id}/messages", dependencies=[Depends(verify_token)])
    async def get_session_messages(session_id: str) -> dict:
        """获取某会话的消息列表。"""
        msgs = await admin_service.get_by_session(session_id)
        return {
            "code": 0,
            "data": [
                {
                    "role": m.role.value if hasattr(m.role, "value") else m.role,
                    "content": m.content,
                    "created_at": m.created_at,
                }
                for m in msgs
            ],
        }

    @router.get("/sessions", dependencies=[Depends(verify_token)])
    async def list_sessions() -> dict:
        return {"code": 0, "data": [], "message": "功能开发中"}

    return router
