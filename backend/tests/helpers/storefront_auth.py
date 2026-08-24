"""前台小程序测试认证辅助函数。"""

from app.service.channels.storefront.auth import StorefrontAuthService


def storefront_auth_headers(user_id: str) -> dict[str, str]:
    """为测试用户签发服务端 Bearer 会话请求头。"""
    token = StorefrontAuthService().issue_access_token(user_id)
    return {"Authorization": f"Bearer {token}"}
