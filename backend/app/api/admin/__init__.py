"""管理后台 API canonical 包入口。

历史代码可继续通过 ``app.api.admin`` 导入鉴权工具和后台根路由。
"""

from app.api.admin.root import (
    ADMIN_SESSION_MAX_AGE_SECONDS,
    ADMIN_SESSION_COOKIE,
    admin_login_is_allowed,
    check_login,
    clear_admin_login_failures,
    create_admin_router,
    has_admin_api_access,
    is_allowed_admin_origin,
    is_valid_admin_session,
    is_valid_admin_token,
    issue_admin_session,
    record_admin_login_failure,
    require_admin_token,
    set_admin_session_cookie,
    verify_token,
)

__all__ = [
    "ADMIN_SESSION_MAX_AGE_SECONDS",
    "ADMIN_SESSION_COOKIE",
    "admin_login_is_allowed",
    "check_login",
    "clear_admin_login_failures",
    "create_admin_router",
    "has_admin_api_access",
    "is_allowed_admin_origin",
    "is_valid_admin_session",
    "is_valid_admin_token",
    "issue_admin_session",
    "record_admin_login_failure",
    "require_admin_token",
    "set_admin_session_cookie",
    "verify_token",
]
