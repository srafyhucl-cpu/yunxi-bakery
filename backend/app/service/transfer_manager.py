"""Human transfer management service."""

import time

import httpx

from app.config import settings
from app.logger import setup_logger
from app.models.transfer import HumanTransfer, TransferStatus
from app.repository.transfer_repo import TransferRepo

logger = setup_logger()

TRANSFER_TIMEOUT_MINUTES = 30
NOTIFY_HTTP_TIMEOUT_SECONDS = 10.0
UNKNOWN_CUSTOMER_NAME = "微信客户（暂未取到昵称）"


class TransferManager:
    """Create transfer tickets and notify servicers."""

    def __init__(self, repo: TransferRepo) -> None:
        self._repo = repo

    async def notify_staff_emergency(
        self,
        session_id: str,
        last_message: str,
        user_id: str = "",
    ) -> None:
        """Push a concise handoff note to the human servicer."""
        call_time = time.strftime("%Y-%m-%d %H:%M:%S")
        customer_name = await self._resolve_customer_name(user_id)
        markdown_content = (
            "### 转人工接手提示\n"
            f"- **客户**: {customer_name}\n"
            f"- **提示**: {last_message or '客户请求人工接待'}\n"
            f"- **时间**: `{call_time}`\n"
            "- **处理**: 请在微信客服接待页继续对话，完整记录可用企微查看接待记录。"
        )

        await self._notify_robot(markdown_content)
        await self._notify_staff_app(markdown_content)

    async def _notify_robot(self, markdown_content: str) -> None:
        if not settings.WECOM_ROBOT_WEBHOOK:
            return
        try:
            async with httpx.AsyncClient(timeout=NOTIFY_HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    settings.WECOM_ROBOT_WEBHOOK,
                    json={
                        "msgtype": "markdown",
                        "markdown": {"content": markdown_content},
                    },
                )
                logger.info("企微群机器人转人工通知结果: %s", resp.text)
        except Exception as exc:
            logger.error("企微群机器人转人工通知失败: %s", exc)

    async def _notify_staff_app(self, markdown_content: str) -> None:
        if not settings.WECOM_CORP_ID or not settings.WECOM_SECRET:
            return
        staff_id = await self._resolve_staff_id()
        if not staff_id:
            logger.warning(
                "转人工接手提示未推送：未配置 WECOM_STAFF_ID 且未找到客服接待人员"
            )
            return

        try:
            from app.service.wecom.client import WECOM_API_BASE, get_wecom_client

            wecom_client = get_wecom_client()
            token = await wecom_client.get_token()

            async with httpx.AsyncClient(timeout=NOTIFY_HTTP_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{WECOM_API_BASE}/message/send",
                    params={"access_token": token},
                    json={
                        "touser": staff_id,
                        "msgtype": "markdown",
                        "agentid": int(settings.WECOM_AGENT_ID or 0),
                        "markdown": {"content": markdown_content},
                    },
                )
                logger.info(
                    "企微客服应用接手提示通知结果 user=%s resp=%s",
                    staff_id,
                    resp.text,
                )
        except Exception as exc:
            logger.error("企微客服应用接手提示通知失败: %s", exc)

    async def _resolve_staff_id(self) -> str:
        if settings.WECOM_STAFF_ID:
            return settings.WECOM_STAFF_ID
        if settings.WECOM_KF_SERVICER_USERID:
            return settings.WECOM_KF_SERVICER_USERID
        try:
            from app.service.wecom.client import get_wecom_client

            wecom_client = get_wecom_client()
            getter = getattr(wecom_client, "_get_first_servicer", None)
            if getter is None:
                return ""
            return str(await getter() or "")
        except Exception as exc:
            logger.error("自动获取客服接待人员失败: %s", exc)
            return ""

    async def _resolve_customer_name(self, user_id: str) -> str:
        if not user_id:
            return UNKNOWN_CUSTOMER_NAME
        try:
            from app.service.wecom.client import get_wecom_client

            wecom_client = get_wecom_client()
            getter = getattr(wecom_client, "get_kf_customer_display_name", None)
            if getter is None:
                return UNKNOWN_CUSTOMER_NAME
            return str(await getter(user_id) or UNKNOWN_CUSTOMER_NAME)
        except Exception as exc:
            logger.warning("获取微信客户名失败 user=%s err=%s", user_id, exc)
            return UNKNOWN_CUSTOMER_NAME

    async def request_transfer(
        self, session_id: str, user_id: str, reason: str = "", summary: str = ""
    ) -> HumanTransfer:
        """Create a transfer ticket and push the handoff note."""
        transfer = await self._repo.create(session_id, user_id, reason, summary)
        logger.info("转人工工单已创建: %s reason=%s", transfer.id, reason)

        await self.notify_staff_emergency(session_id, summary or reason, user_id)

        return transfer

    async def accept_transfer(self, transfer_id: str, staff_id: str) -> None:
        """Mark a transfer ticket as accepted."""
        await self._repo.update_status(transfer_id, TransferStatus.ACCEPTED, staff_id)
        logger.info("转人工已接单: %s staff=%s", transfer_id, staff_id)

    async def close_transfer(self, transfer_id: str) -> None:
        """Mark a transfer ticket as closed."""
        await self._repo.update_status(transfer_id, TransferStatus.CLOSED)
        logger.info("转人工已关闭: %s", transfer_id)

    async def get_pending(self) -> list[HumanTransfer]:
        """Return pending transfer tickets."""
        return await self._repo.get_pending()
