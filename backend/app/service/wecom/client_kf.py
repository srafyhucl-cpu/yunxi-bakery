"""微信客服 API 方法集（Mixin 基类，供 WeComClient 继承）。

职责：
- 调用微信客服专用接口（send_msg / sync_msg / media_upload）
- 与自建应用的 /message/send 完全独立的 API 体系

使用方式：
    class WeComClient(KfClientMixin): ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

# 本文件使用Mixin混入模式（见pyrightconfig.json的overrides配置），
# 运行时通过__bases__动态将KfClientMixin方法注入WeComClient，
# 类型检查已在该文件的overrides中放宽限制

from app.config import settings
from app.logger import setup_logger
from app.service.wecom.constants import WECOM_API_BASE

if TYPE_CHECKING:
    # 前向引用：运行时通过 __bases__ 动态混入，类型检查时需显式导入
    from app.service.wecom.client import WeComClient  # noqa: F401

logger = setup_logger()


class KfClientMixin:
    """微信客服 API 方法集。"""

    async def get_kf_customer_info(
        self: WeComClient,  # type: ignore[reportGeneralTypeIssues]
        external_userid: str,
    ) -> dict[str, Any]:
        """查询微信客服客户基础信息。"""
        if not external_userid:
            return {}
        token = await self.get_token()
        resp = await self._client.post(
            f"{WECOM_API_BASE}/kf/customer/batchget",
            params={"access_token": token},
            json={"external_userid_list": [external_userid]},
        )
        data = resp.json()
        if data.get("errcode") != 0:
            logger.warning(
                "查询微信客服客户基础信息失败 user=%s err=%s",
                external_userid,
                data.get("errmsg"),
            )
            return {}
        customer_list = data.get("customer_list", [])
        return customer_list[0] if customer_list else {}

    async def get_kf_customer_display_name(
        self: WeComClient,  # type: ignore[reportGeneralTypeIssues]
        external_userid: str,
    ) -> str:
        """返回客服可识别的微信客户名，取不到时返回空字符串。"""
        info = await self.get_kf_customer_info(external_userid)
        for key in ("nickname", "name", "remark"):
            value = str(info.get(key, "")).strip()
            if value:
                return value
        return ""

    async def send_kf_text(
        self: WeComClient,  # type: ignore[reportGeneralTypeIssues]
        external_userid: str,
        content: str,
        msgid: str = "",
    ) -> dict:
        """
        发送微信客服文本消息。

        使用 /cgi-bin/kf/send_msg 接口，与自建应用的 /message/send 完全独立。
        """
        token = await self.get_token()
        open_kfid = settings.WECOM_KF_ID

        body: dict[str, Any] = {
            "touser": external_userid,
            "open_kfid": open_kfid,
            "msgtype": "text",
            "text": {"content": content},
        }
        if msgid:
            body["msgid"] = msgid

        resp = await self._client.post(
            f"{WECOM_API_BASE}/kf/send_msg",
            params={"access_token": token},
            json=body,
        )
        response_data = resp.json()

        if response_data.get("errcode") == 0:
            logger.info(
                "客服文本消息已发送 to=%s len=%d", external_userid, len(content)
            )
        else:
            logger.error(
                "客服文本消息发送失败 to=%s err=%s",
                external_userid,
                response_data.get("errmsg"),
            )
        return response_data

    async def send_kf_link(
        self: WeComClient,  # type: ignore[reportGeneralTypeIssues]
        external_userid: str,
        title: str,
        url: str,
        desc: str = "",
        thumb_media_id: str = "",
        msgid: str = "",
    ) -> dict:
        """发送微信客服图文链接消息（用于商品卡片）。"""
        token = await self.get_token()
        open_kfid = settings.WECOM_KF_ID

        body: dict[str, Any] = {
            "touser": external_userid,
            "open_kfid": open_kfid,
            "msgtype": "link",
            "link": {
                "title": title,
                "desc": desc,
                "url": url,
                "thumb_media_id": thumb_media_id,
            },
        }
        if msgid:
            body["msgid"] = msgid

        resp = await self._client.post(
            f"{WECOM_API_BASE}/kf/send_msg",
            params={"access_token": token},
            json=body,
        )
        response_data = resp.json()

        if response_data.get("errcode") == 0:
            logger.info("客服链接消息已发送 to=%s title=%s", external_userid, title)
        else:
            logger.error(
                "客服链接消息发送失败 to=%s title=%s err=%s",
                external_userid,
                title,
                response_data.get("errmsg"),
            )
        return response_data

    async def send_kf_event_text(
        self: WeComClient,  # type: ignore[reportGeneralTypeIssues]
        code: str,
        content: str,
        msgid: str = "",
    ) -> dict:
        """发送微信客服事件响应文本消息。"""
        token = await self.get_token()
        body: dict[str, Any] = {
            "code": code,
            "msgtype": "text",
            "text": {"content": content},
        }
        if msgid:
            body["msgid"] = msgid

        resp = await self._client.post(
            f"{WECOM_API_BASE}/kf/send_msg_on_event",
            params={"access_token": token},
            json=body,
        )
        data = resp.json()
        if data.get("errcode") == 0:
            logger.info("客服事件响应消息已发送 code=%s len=%d", code[:8], len(content))
        else:
            logger.error(
                "客服事件响应消息发送失败 code=%s err=%s",
                code[:8],
                data.get("errmsg"),
            )
        return data

    async def upload_kf_temp_media(
        self: WeComClient,  # type: ignore[reportGeneralTypeIssues]
        file_data: bytes,
        file_type: str = "image",
        file_name: str = "image.jpg",
    ) -> str | None:
        """
        上传临时素材到企微，返回 media_id。

        用于发送 link 图文消息时提供 thumb_media_id。
        临时素材有效期 3 天。

        返回 media_id（字符串），失败返回 None。
        """
        token = await self.get_token()

        # 使用 multipart/form-data 格式上传（httpx files 参数）
        resp = await self._client.post(
            f"{WECOM_API_BASE}/media/upload",
            params={"access_token": token, "type": file_type},
            files={"media": (file_name, file_data, "image/jpeg")},
        )
        data = resp.json()

        if data.get("errcode") == 0:
            media_id = data.get("media_id", "")
            logger.info(
                "临时素材上传成功 type=%s media_id=%s",
                file_type,
                media_id,
            )
            return media_id

        logger.error(
            "临时素材上传失败 type=%s err=%s",
            file_type,
            data.get("errmsg"),
        )
        return None

    async def sync_kf_messages(
        self: WeComClient,  # type: ignore[reportGeneralTypeIssues]
        kf_token: str,
        cursor: str = "",
        limit: int = 1000,
    ) -> dict:
        """拉取微信客服消息（sync_msg 接口）。"""
        token = await self.get_token()
        open_kfid = settings.WECOM_KF_ID

        body: dict[str, Any] = {
            "token": kf_token,
            "open_kfid": open_kfid,
            "limit": limit,
        }
        if cursor:
            body["cursor"] = cursor

        resp = await self._client.post(
            f"{WECOM_API_BASE}/kf/sync_msg",
            params={"access_token": token},
            json=body,
        )
        return resp.json()

    async def download_kf_temp_media(
        self: WeComClient,  # type: ignore[reportGeneralTypeIssues]
        media_id: str,
    ) -> bytes | None:
        """
        从企微下载客服临时素材（图片/语音/视频/文件等）。

        使用 /cgi-bin/media/get 接口下载，返回原始字节。
        临时素材有效期 3 天。

        参数：
            media_id: 素材 media_id（从 sync_msg 消息中获取）
        返回：
            文件字节数据，失败返回 None
        """
        token = await self.get_token()

        resp = await self._client.get(
            f"{WECOM_API_BASE}/media/get",
            params={"access_token": token, "media_id": media_id},
            timeout=30,
        )

        if resp.status_code != 200:
            logger.error(
                "下载临时素材失败 status=%d media_id=%s",
                resp.status_code,
                media_id,
            )
            return None

        data = await resp.aread()
        logger.info(
            "已下载临时素材 size=%dB media_id=%s",
            len(data),
            media_id,
        )
        return data

    # ── 会话状态管理 ──────────────────────────────────────

    async def get_kf_service_state(
        self: WeComClient,  # type: ignore[reportGeneralTypeIssues]
        external_userid: str,
    ) -> int | None:
        """
        查询客服会话状态。

        返回值：
            service_state: 0-未处理 / 1-智能助手 / 2-排队中 / 3-人工接待 / 4-已结束
            出错返回 None
        """
        token = await self.get_token()
        open_kfid = settings.WECOM_KF_ID

        body: dict[str, str] = {
            "open_kfid": open_kfid,
            "external_userid": external_userid,
        }
        resp = await self._client.post(
            f"{WECOM_API_BASE}/kf/service_state/get",
            params={"access_token": token},
            json=body,
        )
        data = resp.json()

        if data.get("errcode") == 0:
            state = data.get("service_state")
            logger.debug("客服会话状态查询 user=%s state=%s", external_userid, state)
            return state
        else:
            logger.error(
                "客服会话状态查询失败 user=%s err=%s",
                external_userid,
                data.get("errmsg"),
            )
            return None

    async def ensure_kf_session_active(
        self: WeComClient,  # type: ignore[reportGeneralTypeIssues]
        external_userid: str,
    ) -> bool:
        """
        确保客服会话处于可发消息的状态。

        企微限制：
          - 状态 0（未处理）：需先分配给智能助手才能 API 发送
          - 状态 1（智能助手）：可以直接 API 发送
          - 状态 2（排队中）：可切换为智能助手
          - 状态 3（人工接待）：只能转接或结束，**无法切回智能助手**
          - 状态 4（已结束）：无法操作

        状态转换规则（官方文档）：
          - 0 → 1 / 2 / 3
          - 1 → 2 / 3
          - 2 → 3
          - 3 → 3（转接）/ 4（结束）
          - 4 → 不可变更（需用户重新发消息）

        返回 True 表示可以发消息，False 表示失败。
        """
        state = await self.get_kf_service_state(external_userid)

        # 状态为 None 表示查询失败，仍尝试发送（让 send_msg 报错更明确）
        if state is None:
            logger.warning("无法查询会话状态，将直接尝试发送 user=%s", external_userid)
            return True

        # 1（智能助手）可以直接发消息
        if state == 1:
            return True

        # 0（未处理）→ 分配给智能助手
        if state == 0:
            return await self._trans_service_state(external_userid, 1)

        # 2（排队中）→ 尝试切换为智能助手
        if state == 2:
            return await self._trans_service_state(external_userid, 1)

        # 3（人工接待）→ 不应干预，由人工客服处理
        #   注意：不能主动结束会话或切换状态，否则会打断人工服务
        if state == 3:
            logger.info(
                "客服会话处于人工接待模式，不发送AI消息 user=%s",
                external_userid,
            )
            return False

        # 4（已结束）
        logger.warning(
            "客服会话已结束，无法发送消息 user=%s state=%d",
            external_userid,
            state,
        )
        return False

    async def _get_first_servicer(self: WeComClient) -> str:  # type: ignore[reportGeneralTypeIssues]
        """
        查询客服账号的接待人员列表，返回第一个可用的 userid。
        返回空字符串表示没有找到可用接待人员。
        """
        token = await self.get_token()
        open_kfid = settings.WECOM_KF_ID

        try:
            # 企微 kf/servicer/list 接口：尝试多种请求方式
            data: dict[str, Any] = {}

            # 方式1: GET + 查询参数
            resp = await self._client.get(
                f"{WECOM_API_BASE}/kf/servicer/list",
                params={"access_token": token, "open_kfid": open_kfid},
            )
            data = resp.json()

            if data.get("errcode") != 0:
                # 方式2: POST + URL参数（open_kfid 在 params 里）
                resp2 = await self._client.post(
                    f"{WECOM_API_BASE}/kf/servicer/list",
                    params={"access_token": token, "open_kfid": open_kfid},
                )
                data = resp2.json()

            if data.get("errcode") != 0:
                logger.error(
                    "查询接待人员列表失败 err=%s %s",
                    data.get("errcode"),
                    data.get("errmsg"),
                )
                return ""

            servicer_list = data.get("servicer_list", [])
            if not servicer_list:
                logger.warning(
                    "客服账号 %s 没有配置任何接待人员，请在企微管理后台添加",
                    open_kfid,
                )
                return ""

            # 取第一个可用接待人员的 userid
            userid = servicer_list[0].get("userid", "")
            if userid:
                logger.info(
                    "自动选择接待人员: %s (共 %d 人)",
                    userid,
                    len(servicer_list),
                )
            return userid

        except Exception as e:
            logger.error("查询接待人员列表异常: %s", e)
            return ""

    async def _trans_service_state(
        self: WeComClient,  # type: ignore[reportGeneralTypeIssues]
        external_userid: str,
        target_state: int,
        servicer_userid: str = "",
    ) -> bool:
        """
        调用 service_state/trans 接口变更会话状态。

        切换到状态3（人工接待）时必须传入 servicer_userid。
        如果未传则自动从企微 API 查询该客服账号的接待人员列表，取第一个。
        """
        token = await self.get_token()
        open_kfid = settings.WECOM_KF_ID

        body: dict[str, Any] = {
            "open_kfid": open_kfid,
            "external_userid": external_userid,
            "service_state": target_state,
        }

        # 切到人工接待(3)必须指定接待人员；未传则动态查询
        if target_state == 3:
            if not servicer_userid:
                # 自动查询客服账号的接待人员列表
                servicer_userid = await self._get_first_servicer()
                if not servicer_userid:
                    logger.error("切到人工接待模式失败：未找到可用接待人员")
                    return False
            body["servicer_userid"] = servicer_userid

        resp = await self._client.post(
            f"{WECOM_API_BASE}/kf/service_state/trans",
            params={"access_token": token},
            json=body,
        )
        data = resp.json()

        state_names = {
            0: "未处理",
            1: "智能助手",
            2: "排队中",
            3: "人工接待",
            4: "已结束",
        }
        target_name = state_names.get(target_state, str(target_state))

        if data.get("errcode") == 0:
            logger.info(
                "客服会话状态切换成功 → %s user=%s", target_name, external_userid
            )
            return True

        logger.error(
            "客服会话状态切换失败 目标=%s user=%s err=%s",
            target_name,
            external_userid,
            data.get("errmsg"),
        )
        return False
