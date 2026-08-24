"""
有赞云 API 客户端。

负责 OAuth2 token 管理和核心业务 API 调用：
- silent grant 获取 access_token（自动续期）
- 客服消息主动推送
- 订单详情查询
- 物流跟踪查询
"""

import asyncio
import time

import httpx

from app.config import settings
from app.exceptions import APIError
from app.logger import setup_logger
from app.repository.config_repo import ConfigRepo

logger = setup_logger()

# ── 有赞云常量 ────────────────────────────────────────────────────────────
YOUZAN_GOODS_H5_BASE_URL = settings.YOUZAN_GOODS_H5_BASE_URL
TOKEN_REFRESH_MARGIN = 300  # 提前 5 分钟刷新（秒）
DEFAULT_TOKEN_EXPIRES_SECONDS = 172_800  # 有赞 token 默认有效期（48 小时）
MOCK_TOKEN_EXPIRES_SECONDS = 86_400  # Mock 模式 token 有效期（24 小时）
USER_QUERY_RESULT_TYPE_MINIAPP = 2  # 用户查询返回结果类型：微信小程序


class YouzanClient:
    """有赞云 API 客户端（单例，管理 access_token 缓存并支持并发刷新锁与仓储持久化）。"""

    def __init__(self, config_repo: ConfigRepo | None = None) -> None:
        self._access_token: str = ""
        self._token_expires_at: float = 0.0
        self._http: httpx.AsyncClient | None = None
        self._lock = asyncio.Lock()
        self._config_repo = config_repo

    @property
    def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            # trust_env=False 禁止从环境变量读取代理，避免无效端口错误
            self._http = httpx.AsyncClient(
                timeout=settings.YOUZAN_HTTP_TIMEOUT_SECONDS, trust_env=False
            )
        return self._http

    async def _refresh_token(self) -> str:
        """通过 OAuth2 silent grant 向有赞云申请 access_token。"""
        if settings.YOUZAN_MOCK_MODE:
            self._access_token = "mock_access_token_123456"
            self._token_expires_at = time.time() + MOCK_TOKEN_EXPIRES_SECONDS
            logger.info("有赞 access_token 已通过 Mock 仿真刷新")
            await self._save_token_to_db(self._access_token)
            return self._access_token

        try:
            resp = await self._client.post(
                settings.YOUZAN_AUTH_URL,
                json={
                    "client_id": settings.YOUZAN_CLIENT_ID,
                    "client_secret": settings.YOUZAN_CLIENT_SECRET,
                    "authorize_type": "silent",
                    "grant_id": settings.YOUZAN_KDT_ID,
                },
            )
            data: dict = resp.json()
        except httpx.HTTPError as exc:
            raise APIError(f"有赞 token 请求失败: {exc}") from exc

        auth_data = data.get("data") if isinstance(data, dict) else None
        token = ""
        expires_in = DEFAULT_TOKEN_EXPIRES_SECONDS

        if isinstance(auth_data, dict):
            token = auth_data.get("access_token", "")
            expires_ms = auth_data.get("expires", 0)
            if expires_ms:
                expires_in = max(60, int((expires_ms / 1000.0) - time.time()))
        else:
            token = data.get("access_token", "")
            expires_in = data.get("expires_in", DEFAULT_TOKEN_EXPIRES_SECONDS)

        if not token:
            raise APIError(f"有赞 token 响应异常: {data}")

        self._access_token = token
        self._token_expires_at = time.time() + expires_in - TOKEN_REFRESH_MARGIN
        logger.info("有赞 access_token 已刷新，有效期 %ds", expires_in)
        await self._save_token_to_db(token)
        return token

    async def _save_token_to_db(self, token: str) -> None:
        """通过 ConfigRepo 安全持久化写入配置数据库。"""
        if self._config_repo is not None:
            try:
                await self._config_repo.set("youzan_access_token", token)
                logger.info("有赞 access_token 已通过 ConfigRepo 写入 shop_config 表")
            except Exception as exc:
                logger.error("有赞 access_token 数据库持久化失败: %s", exc)

    async def get_token(self) -> str:
        """返回有效的 access_token，使用 asyncio.Lock() 做并发刷新互斥。"""
        # 快速路径：Token 未过期则直接返回
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        # 慢速路径：使用 Lock 互斥刷新
        async with self._lock:
            # Double-Checked Locking 双重过滤
            if self._access_token and time.time() < self._token_expires_at:
                return self._access_token
            return await self._refresh_token()

    async def _call(self, api_name: str, version: str, params: dict) -> dict:
        """调用有赞 OpenAPI，自动附加 Bearer token。"""
        if settings.YOUZAN_MOCK_MODE:
            from app.service.youzan.mock_emulator import YouzanMockEmulator

            logger.info("有赞 API 仿真调用拦截 [%s]: %s", api_name, params)
            if api_name == "youzan.scrm.im.conversation.message.create":
                return {"response": {"success": True}}
            elif api_name == "youzan.message.courier.hosting.operate.replymsg":
                return {"response": {"success": True}}
            elif api_name == "youzan.trade.get":
                return YouzanMockEmulator.get_mock_order_response(
                    params.get("tid", "mock_order_123")
                )
            elif api_name == "youzan.express.order.get":
                return YouzanMockEmulator.get_mock_logistics_response(
                    params.get("tid", "mock_order_123")
                )
            elif api_name == "youzan.item.get":
                return YouzanMockEmulator.get_mock_product_response(
                    params.get("item_id", 0), params.get("alias", "")
                )
            elif api_name == "youzan.itemcategories.tags.get":
                return {"data": {"tags": []}}
            elif api_name == "youzan.users.info.query":
                return YouzanMockEmulator.get_mock_user_info_response(
                    str(params.get("mobile", ""))
                )
            elif api_name == "youzan.item.classification.search":
                return {
                    "data": {
                        "items": [],
                        "paginator": {"total_count": 0, "page_no": 1, "page_size": 20},
                    }
                }
            return {"response": {"success": True}}

        token = await self.get_token()
        try:
            resp = await self._client.post(
                f"{settings.YOUZAN_API_BASE}/{api_name}/{version}?access_token={token}",
                json=params,
            )
            result: dict = resp.json()
        except httpx.HTTPError as exc:
            raise APIError(f"有赞 API 调用失败 [{api_name}]: {exc}") from exc

        if resp.status_code != 200:
            raise APIError(f"有赞 API 响应异常 [{api_name}]: {result}")
        return result

    async def call_api(self, api_name: str, version: str, params: dict) -> dict:
        """公开的有赞 OpenAPI 调用入口，供领域子客户端复用鉴权逻辑。"""
        return await self._call(api_name, version, params)

    async def send_reply(self, buyer_open_id: str, content: str) -> dict:
        """主动推送客服消息给买家。"""
        logger.info("有赞客服消息发送: buyer=%s", buyer_open_id)
        return await self._call(
            "youzan.scrm.im.conversation.message.create",
            "3.0.0",
            {
                "kdt_id": settings.YOUZAN_KDT_ID,
                "open_id": buyer_open_id,
                "message_type": "text",
                "content": content,
            },
        )

    async def send_hosting_reply(
        self, conversation_id: str, content: str, msg_type: str = "text"
    ) -> dict:
        """通过有赞客服托管会话回复客户消息。"""
        logger.info("有赞客服托管消息发送: conversation=%s", conversation_id)
        return await self._call(
            "youzan.message.courier.hosting.operate.replymsg",
            "1.0.0",
            {
                "conversationId": conversation_id,
                "msgType": msg_type,
                "content": content,
            },
        )

    async def get_order(self, order_no: str) -> dict:
        """查询订单详情。"""
        logger.info("有赞订单查询: order=%s", order_no)
        return await self._call(
            "youzan.trade.get",
            "4.0.0",
            {"tid": order_no, "kdt_id": settings.YOUZAN_KDT_ID},
        )

    async def query_user_info(self, mobile: str) -> dict:
        """按手机号查询有赞用户信息（返回微信 openid/unionid 等平台账号）。"""
        logger.info("有赞用户信息查询: mobile=%s", mobile)
        return await self._call(
            "youzan.users.info.query",
            "1.0.0",
            {"mobile": mobile, "result_type_list": [USER_QUERY_RESULT_TYPE_MINIAPP]},
        )

    async def get_logistics(self, order_no: str) -> dict:
        """查询物流跟踪信息。"""
        logger.info("有赞物流查询: order=%s", order_no)
        return await self._call(
            "youzan.express.order.get",
            "3.0.0",
            {"tid": order_no, "kdt_id": settings.YOUZAN_KDT_ID},
        )

    async def get_product(self, item_id: int | str = 0, alias: str = "") -> dict:
        """根据商品 ID 或别名查询单品规格与实时库存。"""
        logger.info("有赞单品查询: item_id=%s, alias=%s", item_id, alias)
        params: dict = {"kdt_id": settings.YOUZAN_KDT_ID}
        if item_id:
            try:
                params["item_id"] = int(item_id)
            except (ValueError, TypeError) as exc:
                raise ValueError(
                    f"商品ID格式非法，期望纯数字，实际值: {item_id!r}"
                ) from exc
        if alias:
            params["alias"] = alias
        return await self._call(
            "youzan.item.get",
            "3.0.0",
            params,
        )

    async def list_onsale_items(self) -> list[dict]:
        """分页拉取有赞在售商品完整列表（含 sold_num）。"""
        if settings.YOUZAN_MOCK_MODE:
            logger.info("有赞在售商品列表仿真拦截，返回空列表")
            return []

        page_no = 1
        page_size = 100
        all_items: list[dict] = []
        while True:
            result = await self._call(
                "youzan.items.onsale.get",
                "3.0.1",
                {
                    "kdt_id": settings.YOUZAN_KDT_ID,
                    "page_no": page_no,
                    "page_size": page_size,
                },
            )
            response = result.get("data") or result.get("response") or {}
            items: list[dict] = response.get("items") or []
            all_items.extend(items)
            total_results = int(
                response.get("count") or response.get("total_results") or 0
            )
            if page_no * page_size >= total_results or not items:
                break
            page_no += 1
        logger.info("有赞在售商品全量拉取完成，共 %d 条", len(all_items))
        return all_items

    async def list_product_tags(self) -> list[dict]:
        """拉取有赞商品分组标签列表。"""
        if settings.YOUZAN_MOCK_MODE:
            logger.info("有赞商品分组列表仿真拦截，返回空列表")
            return []

        result = await self._call(
            "youzan.itemcategories.tags.get",
            "3.0.0",
            {"kdt_id": settings.YOUZAN_KDT_ID},
        )
        response = result.get("data") or result.get("response") or {}
        tags: list[dict] = response.get("tags") or []
        logger.info("有赞商品分组拉取完成，共 %d 个", len(tags))
        return tags

    async def list_onsale_item_ids(self) -> set[int]:
        """分页拉取有赞店铺所有在售商品的 item_id 集合。"""
        items = await self.list_onsale_items()
        item_ids: set[int] = set()
        for item in items:
            try:
                item_ids.add(int(item["item_id"]))
            except (KeyError, ValueError, TypeError):
                continue
        return item_ids

    async def search_item_base(self, item_ids: list[int]) -> list[dict]:
        """批量查询有赞商品基础信息，补齐商品分类与分组 ID。"""
        if settings.YOUZAN_MOCK_MODE:
            logger.info("有赞商品基础信息批量查询仿真拦截，返回空列表")
            return []
        if not item_ids:
            return []

        result = await self._call(
            "youzan.item.base.search",
            "1.0.0",
            {
                "kdt_id": settings.YOUZAN_KDT_ID,
                "channel": 0,
                "item_ids": item_ids[:20],
            },
        )
        response = result.get("data") or result.get("response") or {}
        items = (
            response.get("items")
            or response.get("item_list")
            or response.get("list")
            or []
        )
        if not isinstance(items, list):
            return []
        logger.info("有赞商品基础信息批量查询完成，共 %d 条", len(items))
        return items

    async def search_item_classifications(self) -> list[dict]:
        """分页查询有赞商品分类，返回 classification_id 与中文名称。"""
        if settings.YOUZAN_MOCK_MODE:
            logger.info("有赞商品分类搜索仿真拦截，返回空列表")
            return []

        page_no = 1
        page_size = 20
        all_items: list[dict] = []
        while True:
            result = await self._call(
                "youzan.item.classification.search",
                "1.0.0",
                {
                    "request": {
                        "kdt_id": settings.YOUZAN_KDT_ID,
                        "page_no": page_no,
                    },
                },
            )
            response = result.get("data") or result.get("response") or {}
            items = response.get("items") or []
            if not isinstance(items, list):
                break
            all_items.extend(items)
            paginator = response.get("paginator") or {}
            total_count = int(paginator.get("total_count") or len(all_items))
            page_size = int(paginator.get("page_size") or page_size)
            if page_no * page_size >= total_count or not items:
                break
            page_no += 1
        logger.info("有赞商品分类搜索完成，共 %d 个分类", len(all_items))
        return all_items

    async def close(self) -> None:
        """关闭 HTTP 连接池。"""
        if self._http:
            await self._http.aclose()
            self._http = None
