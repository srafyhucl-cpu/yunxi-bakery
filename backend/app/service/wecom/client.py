"""企微 API 客户端。

职责：
- 缓存并自动刷新 access_token（2 小时过期）
- 调用客户联系消息推送接口发送消息
- 微信客服消息发送（通过 KfClientMixin 混入）
"""

import asyncio
import time

import httpx

from app.config import settings
from app.logger import setup_logger
from app.service.wecom.client_kf import KfClientMixin
from app.service.wecom.constants import WECOM_API_BASE

logger = setup_logger()

# access_token 提前 5 分钟刷新
TOKEN_REFRESH_MARGIN = 300


class WeComClient(KfClientMixin):
    """企微 API 客户端（单例，管理 access_token 缓存）。"""

    def __init__(self) -> None:
        self._token: str = ""
        self._token_expires_at: float = 0
        self._http: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()

    @property
    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                timeout=httpx.Timeout(settings.WECOM_HTTP_TIMEOUT_SECONDS)
            )
        return self._http

    async def _fetch_token(self) -> str:
        """向企微获取新的 access_token。"""
        resp = await self._client.get(
            f"{WECOM_API_BASE}/gettoken",
            params={
                "corpid": settings.WECOM_CORP_ID,
                "corpsecret": settings.WECOM_SECRET,
            },
        )
        response_data = resp.json()
        if response_data.get("errcode") != 0:
            raise RuntimeError(
                f"获取 access_token 失败: {response_data.get('errmsg', 'unknown')}"
            )
        token: str = response_data["access_token"]
        expires_in: int = response_data.get("expires_in", 7200)
        self._token = token
        self._token_expires_at = time.time() + expires_in - TOKEN_REFRESH_MARGIN
        logger.info("WeCom access_token 刷新成功（并发锁保护），有效期 %ds", expires_in)
        return token

    async def get_token(self) -> str:
        """获取有效的 access_token（双重检查锁保护并发安全）。"""
        # 快速路径：缓存有效直接返回（无锁开销）
        if self._token and time.time() < self._token_expires_at:
            return self._token
        # 慢路径：带锁并发限制，防止多协程同时刷新
        async with self._lock:
            # 双重检验：排队等待的协程无需重复刷新
            if self._token and time.time() < self._token_expires_at:
                return self._token
            return await self._fetch_token()

    async def send_text(
        self,
        user_id: str,
        content: str,
        agent_id: str | None = None,
    ) -> dict:
        """
        发送文本消息（自动适配内部成员/外部联系人）。

        参数：
            user_id: 用户 userid（内部成员或外部联系人）
            content: 消息内容
            agent_id: 应用 AgentId（默认从配置读取）
        返回：
            API 响应 JSON
        """
        token = await self.get_token()
        agentid = int(agent_id or settings.WECOM_AGENT_ID)

        # 先尝试内部消息接口（适用于企业成员）
        resp = await self._client.post(
            f"{WECOM_API_BASE}/message/send",
            params={"access_token": token},
            json={
                "touser": user_id,
                "msgtype": "text",
                "agentid": agentid,
                "text": {"content": content},
            },
        )
        response_data = resp.json()

        # 如果内部接口失败且是用户不存在类错误，降级尝试外部联系人接口
        if response_data.get("errcode") != 0:
            errcode = response_data.get("errcode")
            # 常见的不存在/无权限错误码，尝试外部联系人接口
            if errcode in (60001, 60002, 60004, 60005, 60006, 81003, 81006):
                logger.info(
                    "内部消息发送失败(err=%d)，降级尝试外部联系人接口 user=%s",
                    errcode,
                    user_id,
                )
                resp = await self._client.post(
                    f"{WECOM_API_BASE}/externalcontact/message/send",
                    params={"access_token": token},
                    json={
                        "to_user": user_id,
                        "msgtype": "text",
                        "agent_id": agentid,
                        "text": {"content": content},
                    },
                )
                response_data = resp.json()

        if response_data.get("errcode") == 0:
            logger.info("消息已发送 to=%s len=%d", user_id, len(content))
        else:
            logger.error(
                "消息发送失败 to=%s err=%s", user_id, response_data.get("errmsg")
            )
        return response_data

    async def send_markdown(
        self,
        user_id: str,
        content: str,
        agent_id: str | None = None,
    ) -> dict:
        """发送 Markdown 消息（自动适配内部/外部）。"""
        token = await self.get_token()
        agentid = int(agent_id or settings.WECOM_AGENT_ID)

        resp = await self._client.post(
            f"{WECOM_API_BASE}/message/send",
            params={"access_token": token},
            json={
                "touser": user_id,
                "msgtype": "markdown",
                "agentid": agentid,
                "markdown": {"content": content},
            },
        )
        response_data = resp.json()

        if response_data.get("errcode") != 0 and response_data.get("errcode") in (
            60001,
            60002,
            60004,
            60005,
            60006,
            81003,
            81006,
        ):
            resp = await self._client.post(
                f"{WECOM_API_BASE}/externalcontact/message/send",
                params={"access_token": token},
                json={
                    "to_user": user_id,
                    "msgtype": "markdown",
                    "agent_id": agentid,
                    "markdown": {"content": content},
                },
            )
            response_data = resp.json()

        if response_data.get("errcode") != 0:
            logger.error("Markdown 发送失败 err=%s", response_data.get("errmsg"))
        return response_data

    async def send_news(
        self,
        user_id: str,
        title: str,
        description: str = "",
        url: str = "",
        pic_url: str = "",
        agent_id: str | None = None,
    ) -> dict:
        """
        发送图文消息（news），用于商品卡片等场景。

        参数：
            user_id: 用户 userid
            title: 图文标题
            description: 图文描述
            url: 点击跳转链接
            pic_url: 封面图片 URL
            agent_id: 应用 AgentId
        返回：
            API 响应 JSON
        """
        token = await self.get_token()
        agentid = int(agent_id or settings.WECOM_AGENT_ID)

        news_body = {
            "articles": [
                {
                    "title": title,
                    "description": description,
                    "url": url,
                    "picurl": pic_url,
                }
            ]
        }

        # 优先使用内部接口
        resp = await self._client.post(
            f"{WECOM_API_BASE}/message/send",
            params={"access_token": token},
            json={
                "touser": user_id,
                "msgtype": "news",
                "agentid": agentid,
                "news": news_body,
            },
        )
        response_data = resp.json()

        # 失败时降级到外部联系人接口
        if response_data.get("errcode") != 0 and response_data.get("errcode") in (
            60001,
            60002,
            60004,
            60005,
            60006,
            81003,
            81006,
        ):
            resp = await self._client.post(
                f"{WECOM_API_BASE}/externalcontact/message/send",
                params={"access_token": token},
                json={
                    "to_user": user_id,
                    "msgtype": "news",
                    "agent_id": agentid,
                    "news": news_body,
                },
            )
            response_data = resp.json()

        if response_data.get("errcode") == 0:
            logger.info("图文消息已发送 to=%s title=%s", user_id, title)
        else:
            logger.error(
                "图文消息发送失败 to=%s title=%s err=%s",
                user_id,
                title,
                response_data.get("errmsg"),
            )
        return response_data

    async def close(self) -> None:
        """关闭 HTTP 客户端。"""
        if self._http:
            await self._http.aclose()
            self._http = None


# 全局单例
_client: WeComClient | None = None


def get_wecom_client() -> WeComClient:
    """获取全局 WeComClient 单例。"""
    global _client
    if _client is None:
        _client = WeComClient()
    return _client


async def close_wecom_client() -> None:
    """关闭全局客户端（应用退出时调用）。"""
    global _client
    if _client:
        await _client.close()
        _client = None
