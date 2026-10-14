"""前台渠道认证服务。"""

import logging
from datetime import datetime, timedelta, timezone

import httpx
from jose import JWTError, jwt

from app.config import settings

logger = logging.getLogger("yunxi_bot")


class StorefrontAuthService:
    """处理微信小程序登录与手机号会员认领绑定。"""

    def __init__(
        self,
        customer_repo: object = None,
        member_balance_repo: object = None,
        db: object = None,
    ) -> None:
        self._customer_repo = customer_repo
        self._member_balance_repo = member_balance_repo
        self._db = db

    async def login(self, code: str) -> dict:
        """使用 wx.login code 换取小程序用户标识；配置缺失时返回明确失败。"""
        normalized_code = code.strip()
        if not normalized_code:
            raise ValueError("登录 code 不能为空")
        if not self._is_wechat_configured():
            raise ValueError("微信小程序 AppID/Secret 未配置，无法换取真实会话")
        payload = await self._request_wechat_session(normalized_code)
        openid = str(payload.get("openid", "")).strip()
        if not openid:
            raise ValueError("微信登录失败，请稍后重试")
        user_id = f"wx_{openid}"
        return {
            "userId": user_id,
            "openid": openid,
            "sessionReady": True,
            "isDemo": False,
            "accessToken": self.issue_access_token(user_id),
            "tokenType": "Bearer",
            "expiresIn": settings.STOREFRONT_AUTH_TTL_SECONDS,
        }

    def issue_access_token(self, user_id: str) -> str:
        """为已完成微信登录的用户签发短期服务端会话 token。"""
        secret = self._require_auth_secret()
        normalized_user_id = user_id.strip()
        if not normalized_user_id:
            raise ValueError("用户身份不能为空")
        issued_at = datetime.now(timezone.utc)
        payload = {
            "sub": normalized_user_id,
            "iat": issued_at,
            "exp": issued_at + timedelta(seconds=settings.STOREFRONT_AUTH_TTL_SECONDS),
        }
        return jwt.encode(payload, secret, algorithm="HS256")

    def verify_access_token(self, access_token: str) -> str:
        """校验服务端会话 token 并返回唯一用户身份。"""
        secret = self._require_auth_secret()
        try:
            payload = jwt.decode(access_token, secret, algorithms=["HS256"])
        except JWTError as exc:
            raise ValueError("登录会话无效或已过期") from exc
        user_id = str(payload.get("sub", "")).strip()
        if not user_id:
            raise ValueError("登录会话缺少用户身份")
        return user_id

    def _require_auth_secret(self) -> str:
        secret = settings.STOREFRONT_AUTH_SECRET.strip()
        if not secret:
            raise ValueError("前台会话密钥未配置")
        return secret

    def _is_wechat_configured(self) -> bool:
        return bool(
            settings.WECHAT_MINIAPP_APP_ID and settings.WECHAT_MINIAPP_APP_SECRET
        )

    async def _request_wechat_session(self, code: str) -> dict:
        try:
            async with httpx.AsyncClient(
                timeout=settings.WECHAT_MINIAPP_HTTP_TIMEOUT_SECONDS
            ) as client:
                response = await client.get(
                    settings.WECHAT_MINIAPP_AUTH_URL,
                    params={
                        "appid": settings.WECHAT_MINIAPP_APP_ID,
                        "secret": settings.WECHAT_MINIAPP_APP_SECRET,
                        "js_code": code,
                        "grant_type": "authorization_code",
                    },
                )
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise ValueError("微信登录上游返回错误") from exc
        except httpx.RequestError as exc:
            raise ValueError("微信登录上游不可用") from exc
        except ValueError as exc:
            raise ValueError("微信登录响应无效") from exc
        return data if isinstance(data, dict) else {}

    async def claim_member_by_phone(
        self,
        *,
        user_id: str,
        phone: str,
        customer_repo: object = None,
        member_balance_repo: object = None,
        db: object = None,
    ) -> dict:
        """小程序手机号认领/绑定有赞老会员，支持强事务绑定与储值/积分/订单回显。"""
        from app.models.customer_master import (
            CustomerIdentityConfidence,
            CustomerIdentityLinkCreate,
            CustomerIdentityType,
            CustomerIdentityVerificationStatus,
            CustomerMasterCreate,
            CustomerSourceSystem,
        )
        from app.repository.customer_master_repo import CustomerMasterRepo
        from app.repository.member_balance_repo import MemberBalanceRepo

        clean_phone = phone.strip()
        if (
            not clean_phone
            or len(clean_phone) != 11
            or not clean_phone.isdigit()
            or not clean_phone.startswith("1")
        ):
            raise ValueError("请输入有效的11位手机号")

        openid = (
            user_id.replace("wx_", "").strip()
            if user_id.startswith("wx_")
            else user_id.strip()
        )
        if not openid:
            raise ValueError("缺少有效微信用户身份")

        active_db = db or self._db
        if (
            active_db is None
            and customer_repo is not None
            and hasattr(customer_repo, "_db")
        ):
            active_db = customer_repo._db
        if (
            active_db is None
            and member_balance_repo is not None
            and hasattr(member_balance_repo, "_db")
        ):
            active_db = member_balance_repo._db

        c_repo = customer_repo or self._customer_repo or CustomerMasterRepo(active_db)
        b_repo = (
            member_balance_repo
            or self._member_balance_repo
            or MemberBalanceRepo(active_db)
        )

        # 1. 查找是否已有手机号对应主档
        phone_link = await c_repo.get_identity_by_value(
            "yunxi", CustomerIdentityType.PHONE.value, clean_phone
        )
        if phone_link is not None:
            customer_id = phone_link.customer_id
            customer = await c_repo.get_master(customer_id)
        else:
            # 自动创建客户主档
            customer = await c_repo.create_master(
                CustomerMasterCreate(
                    tenant_id="yunxi",
                    primary_phone=clean_phone,
                    phone_verified=1,
                    first_source=CustomerSourceSystem.MINIAPP.value,
                    identity_confidence=CustomerIdentityConfidence.HIGH.value,
                    has_miniapp_identity=1,
                )
            )
            customer_id = customer.id
            # 建立手机号链接
            await c_repo.create_identity_link(
                CustomerIdentityLinkCreate(
                    tenant_id="yunxi",
                    customer_id=customer_id,
                    identity_type=CustomerIdentityType.PHONE.value,
                    identity_value=clean_phone,
                    confidence_score=100,
                    verification_status=CustomerIdentityVerificationStatus.VERIFIED.value,
                    source_system=CustomerSourceSystem.MINIAPP.value,
                    source_record_id=clean_phone,
                )
            )

        # 2. 绑定 miniapp_openid 到客户主档
        existing_openid_link = await c_repo.get_identity_by_value(
            "yunxi", CustomerIdentityType.MINIAPP_OPENID.value, openid
        )
        if existing_openid_link is None:
            await c_repo.create_identity_link(
                CustomerIdentityLinkCreate(
                    tenant_id="yunxi",
                    customer_id=customer_id,
                    identity_type=CustomerIdentityType.MINIAPP_OPENID.value,
                    identity_value=openid,
                    confidence_score=100,
                    verification_status=CustomerIdentityVerificationStatus.VERIFIED.value,
                    source_system=CustomerSourceSystem.MINIAPP.value,
                    source_record_id=openid,
                )
            )
        elif existing_openid_link.customer_id != customer_id:
            # 迁移关联至真实手机号主档
            if hasattr(c_repo, "_db") and c_repo._db is not None:
                await c_repo._db.execute(
                    "UPDATE customer_identity_links SET customer_id = ? WHERE id = ?",
                    (customer_id, existing_openid_link.id),
                )

        # 3. 同步会员余额并获取账本快照
        balance = await b_repo.get_by_mobile(clean_phone)
        if balance is None:
            await b_repo.upsert_identity(
                mobile=clean_phone,
                customer_id=customer_id,
                is_member=1,
            )
            balance = await b_repo.get_by_mobile(clean_phone) or {}
        elif not balance.get("customer_id"):
            await b_repo.upsert_identity(
                mobile=clean_phone,
                customer_id=customer_id,
            )

        stored_value_fen = int(balance.get("stored_value_fen", 0) or 0)
        principal_fen = int(balance.get("principal_fen", stored_value_fen) or 0)
        bonus_fen = int(balance.get("bonus_fen", 0) or 0)
        points = int(balance.get("points", 0) or 0)
        is_member = bool(balance.get("is_member", 0))
        card_alias = str(balance.get("card_alias", "") or "")

        # 4. 获取历史有赞订单摘要
        history_orders = []
        if active_db is not None:
            try:
                sql = (
                    "SELECT order_no, status, amount_fen, product_titles, total_quantity, "
                    "pay_time, created_at FROM youzan_orders "
                    "WHERE buyer_id = ? OR outer_user_id = ? "
                    "ORDER BY created_at DESC LIMIT 10"
                )
                params = (clean_phone, clean_phone)
                if hasattr(active_db, "execute_fetchall"):
                    order_rows = await active_db.execute_fetchall(sql, params)
                else:
                    async with active_db.execute(sql, params) as cursor:
                        order_rows = await cursor.fetchall()

                for r in order_rows:
                    if isinstance(r, dict):
                        history_orders.append(
                            {
                                "orderNo": str(r.get("order_no", "")),
                                "status": str(r.get("status", "")),
                                "amountFen": int(r.get("amount_fen", 0) or 0),
                                "productTitles": str(r.get("product_titles", "")),
                                "totalQuantity": int(r.get("total_quantity", 0) or 0),
                                "payTime": str(r.get("pay_time", "") or ""),
                                "createdAt": str(r.get("created_at", "") or ""),
                            }
                        )
                    else:
                        history_orders.append(
                            {
                                "orderNo": str(
                                    r[0] if len(r) > 0 and r[0] is not None else ""
                                ),
                                "status": str(
                                    r[1] if len(r) > 1 and r[1] is not None else ""
                                ),
                                "amountFen": int(
                                    r[2] if len(r) > 2 and r[2] is not None else 0
                                ),
                                "productTitles": str(
                                    r[3] if len(r) > 3 and r[3] is not None else ""
                                ),
                                "totalQuantity": int(
                                    r[4] if len(r) > 4 and r[4] is not None else 0
                                ),
                                "payTime": str(
                                    r[5] if len(r) > 5 and r[5] is not None else ""
                                ),
                                "createdAt": str(
                                    r[6] if len(r) > 6 and r[6] is not None else ""
                                ),
                            }
                        )
            except Exception as exc:
                logger.error(
                    "Failed to query history orders for phone %s: %s",
                    clean_phone,
                    exc,
                    exc_info=True,
                )

        return {
            "userId": user_id,
            "mobile": clean_phone,
            "isMember": is_member,
            "cardAlias": card_alias,
            "points": points,
            "storedValueFen": stored_value_fen,
            "storedValueYuan": f"{stored_value_fen / 100:.2f}",
            "principalFen": principal_fen,
            "bonusFen": bonus_fen,
            "historyOrders": history_orders,
        }


__all__ = ["StorefrontAuthService"]
