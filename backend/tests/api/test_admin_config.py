import pytest

from app.api.admin_config import create_shop_config_router
from app.config import settings


def _get_route_endpoint(router, path: str, method: str):
    for route in router.routes:
        if getattr(route, "path", "") == path and method in getattr(
            route, "methods", set()
        ):
            return route.endpoint
    raise AssertionError(f"Route not found: {method} {path}")


class _FakeAdminService:
    async def get_settings_summary(self) -> dict:
        return {
            "shop": {"featured_product_count": 2},
            "channels": {"youzan": {"mock_mode": True}},
            "api": {"admin_token_configured": True},
        }


@pytest.mark.asyncio
async def test_admin_settings_summary_requires_token() -> None:
    router = create_shop_config_router(_FakeAdminService())
    endpoint = _get_route_endpoint(router, "/api/v1/admin/settings/summary", "GET")

    payload = await endpoint(authorization=f"Bearer {settings.ADMIN_API_TOKEN}")

    assert payload["code"] == 0
    assert payload["data"]["shop"]["featured_product_count"] == 2
    assert payload["data"]["channels"]["youzan"]["mock_mode"] is True
