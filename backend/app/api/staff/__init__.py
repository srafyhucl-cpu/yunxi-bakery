"""店员 API canonical 包入口。"""

from app.api.staff._auth import (
    STAFF_SESSION_COOKIE,
    build_staff_dependency,
    clear_staff_session_cookie,
    require_staff,
    set_staff_session_cookie,
)
from app.api.staff.auth import create_staff_auth_router
from app.api.staff.quick_order import create_staff_quick_order_router

__all__ = [
    "STAFF_SESSION_COOKIE",
    "build_staff_dependency",
    "clear_staff_session_cookie",
    "create_staff_auth_router",
    "create_staff_quick_order_router",
    "require_staff",
    "set_staff_session_cookie",
]
