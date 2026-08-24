"""后台主推商品到小程序商品目录联动测试。"""

import importlib

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.miniapp_catalog import create_miniapp_catalog_router
from app.config import settings
from app.repository.config_repo import ConfigRepo
from app.repository.content_change_history_repo import ContentChangeHistoryRepo
from app.repository.knowledge_admin_repo import KnowledgeAdminRepo
from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.message_repo import MessageRepo
from app.repository.session_repo import SessionRepo
from app.repository.transfer_repo import TransferRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.admin import AdminService
from app.service.catalog import CatalogApplicationService
from tests.helpers.miniapp_catalog_seed import seed_miniapp_product


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建同时包含后台主推配置和小程序商品目录的测试应用。"""
    admin_config = importlib.import_module("app.api.admin_config")
    admin_config = importlib.reload(admin_config)

    test_app = FastAPI()
    config_repo = ConfigRepo(db)
    knowledge_repo = KnowledgeRepo(db)
    product_repo = KnowledgeProductRepo(db)
    youzan_product_repo = YouzanProductRepo(db)
    admin_service = AdminService(
        session_repo=SessionRepo(db),
        message_repo=MessageRepo(db),
        transfer_repo=TransferRepo(db),
        knowledge_repo=knowledge_repo,
        config_repo=config_repo,
        youzan_product_repo=youzan_product_repo,
        knowledge_product_repo=product_repo,
        knowledge_admin_repo=KnowledgeAdminRepo(db),
        history_repo=ContentChangeHistoryRepo(db),
    )
    catalog_service = CatalogApplicationService(
        product_repo=product_repo,
        knowledge_repo=knowledge_repo,
        config_repo=config_repo,
    )

    test_app.include_router(admin_config.create_shop_config_router(admin_service))
    test_app.include_router(create_miniapp_catalog_router(catalog_service))
    return test_app


@pytest.mark.asyncio
async def test_admin_featured_products_drive_miniapp_featured_catalog(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """后台保存主推商品后，小程序 featured 商品列表应读取同一份配置。"""
    await seed_miniapp_product(db, item_id=72001, title="后台主推草莓蛋糕")
    await seed_miniapp_product(db, item_id=72002, title="后台主推芒果千层")
    await seed_miniapp_product(db, item_id=72003, title="普通在售蛋糕")
    headers = {"Authorization": f"Bearer {settings.ADMIN_API_TOKEN}"}
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        denied = await client.post(
            "/api/v1/admin/shop-config/featured-products",
            json={"products": ["后台主推草莓蛋糕"]},
        )
        assert denied.status_code == 401

        saved = await client.post(
            "/api/v1/admin/shop-config/featured-products",
            json={
                "products": [
                    " 后台主推芒果千层 ",
                    "",
                    "后台主推草莓蛋糕",
                ],
            },
            headers=headers,
        )
        assert saved.status_code == 200
        assert saved.json()["data"] == ["后台主推芒果千层", "后台主推草莓蛋糕"]

        admin_featured = await client.get(
            "/api/v1/admin/products",
            params={"featured_only": "true"},
            headers=headers,
        )
        assert admin_featured.status_code == 200
        assert [item["title"] for item in admin_featured.json()["data"]] == [
            "后台主推芒果千层",
            "后台主推草莓蛋糕",
        ]

        miniapp_featured = await client.get(
            "/api/v1/miniapp/products",
            params={"featured": "true"},
        )
        assert miniapp_featured.status_code == 200
        assert [item["title"] for item in miniapp_featured.json()["data"]] == [
            "后台主推芒果千层",
            "后台主推草莓蛋糕",
        ]
