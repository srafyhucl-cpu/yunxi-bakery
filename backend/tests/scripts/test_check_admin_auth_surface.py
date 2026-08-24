"""后台认证前端静态合同测试。"""

from scripts.check_admin_auth_surface import check


def test_admin_auth_surface_is_cookie_only() -> None:
    """后台前端认证面必须保持短会话 Cookie-only。"""
    assert check() == []
