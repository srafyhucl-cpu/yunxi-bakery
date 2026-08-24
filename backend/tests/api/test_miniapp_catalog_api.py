"""小程序商品目录 API 测试。"""

import aiosqlite
import httpx
import pytest
from fastapi import FastAPI

from app.api.miniapp_catalog import create_miniapp_catalog_router
from app.models.config import FEATURED_PRODUCTS_KEY
from app.repository.config_repo import ConfigRepo
from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.catalog import CatalogApplicationService
from tests.helpers.miniapp_catalog_seed import seed_miniapp_product


class _FakeImageResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        content: bytes = b"fake-image",
        content_type: str = "image/jpeg",
    ) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = {
            "content-type": content_type,
            "content-length": str(len(content)),
        }

    async def __aenter__(self) -> "_FakeImageResponse":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def aiter_bytes(self):
        yield self.content


class _FakeImageClient:
    requested_urls: list[str] = []
    response = _FakeImageResponse()

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> "_FakeImageClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    def stream(self, method: str, url: str) -> _FakeImageResponse:
        assert method == "GET"
        self.requested_urls.append(url)
        return self.response


@pytest.fixture
def app(db: aiosqlite.Connection) -> FastAPI:
    """构建只包含商品目录路由的测试应用。"""
    test_app = FastAPI()
    service = CatalogApplicationService(
        product_repo=KnowledgeProductRepo(db),
        knowledge_repo=KnowledgeRepo(db),
        config_repo=ConfigRepo(db),
        youzan_product_repo=YouzanProductRepo(db),
    )
    test_app.include_router(create_miniapp_catalog_router(service))
    return test_app


@pytest.mark.asyncio
async def test_miniapp_products_api_lists_filters_and_reads_detail(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """商品列表、装修 ID 过滤、主推过滤和详情读取应走同一条公开 API 链路。"""
    await seed_miniapp_product(
        db,
        item_id=71001,
        title="API 草莓蛋糕",
        content="当季草莓搭配动物奶油，适合生日和家庭聚会。",
        keywords="生日蛋糕,草莓",
        price_fen=26800,
        stock=6,
        sold_num=12,
        image="https://img.example/api-strawberry.jpg",
        tag_ids=["281476346"],
        category_title="生日蛋糕",
    )
    await seed_miniapp_product(db, item_id=71002, title="API 芒果千层")
    await seed_miniapp_product(db, item_id=71003, title="API 下架蛋糕", is_active=0)
    await ConfigRepo(db).set_list(FEATURED_PRODUCTS_KEY, ["API 芒果千层"])

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        list_response = await client.get("/api/v1/miniapp/products")
        assert list_response.status_code == 200
        products = list_response.json()["data"]
        assert {product["id"] for product in products} == {"71001", "71002"}

        shelf_response = await client.get(
            "/api/v1/miniapp/products",
            params={"ids": "71001,missing,71002,71001"},
        )
        assert shelf_response.status_code == 200
        assert [product["id"] for product in shelf_response.json()["data"]] == [
            "71001",
            "71002",
        ]

        featured_response = await client.get(
            "/api/v1/miniapp/products",
            params={"featured": "true"},
        )
        assert featured_response.status_code == 200
        assert [product["title"] for product in featured_response.json()["data"]] == [
            "API 芒果千层"
        ]

        detail_response = await client.get("/api/v1/miniapp/products/71001")
        assert detail_response.status_code == 200
        detail = detail_response.json()["data"]
        assert detail["title"] == "API 草莓蛋糕"
        assert detail["imageUrl"] == "/api/v1/miniapp/products/71001/image"
        assert detail["priceFen"] == 26800
        assert detail["soldText"] == "已售 12"
        assert detail["categoryId"] == "youzan-tag-281476346"
        assert detail["categoryName"] == "生日蛋糕"
        assert detail["tags"] == ["生日蛋糕", "草莓"]

        categories_response = await client.get("/api/v1/miniapp/product-categories")
        assert categories_response.status_code == 200
        assert categories_response.json()["data"] == [
            {
                "id": "youzan-tag-281476346",
                "title": "生日蛋糕",
                "sort": 10,
                "productCount": 1,
            }
        ]

        category_response = await client.get(
            "/api/v1/miniapp/products",
            params={"categoryId": "youzan-tag-281476346"},
        )
        assert category_response.status_code == 200
        assert [product["id"] for product in category_response.json()["data"]] == [
            "71001"
        ]


@pytest.mark.asyncio
async def test_miniapp_products_api_hides_generic_youzan_category(
    db: aiosqlite.Connection,
    app: FastAPI,
) -> None:
    """小程序商品接口不应把有赞泛化标签透出成分类。"""
    await seed_miniapp_product(
        db,
        item_id=71004,
        title="API 泛化标签商品",
        keywords="商品,价格,在售",
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/miniapp/products")

    assert response.status_code == 200
    product = response.json()["data"][0]
    assert product["categoryId"] == "youzan-products"
    assert product["categoryName"] == "有赞同步商品"


@pytest.mark.asyncio
async def test_miniapp_product_image_proxy_fetches_configured_product_image(
    db: aiosqlite.Connection,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """商品图片代理只按已存在商品 ID 拉取后端配置的原始图片。"""
    await seed_miniapp_product(
        db,
        item_id=72001,
        title="图片代理草莓蛋糕",
        image="https://img.example/proxy-strawberry.jpg",
    )
    _FakeImageClient.requested_urls = []
    _FakeImageClient.response = _FakeImageResponse(
        content=b"\xff\xd8cake-image",
        content_type="image/jpeg",
    )
    monkeypatch.setattr("app.service.catalog.application.AsyncClient", _FakeImageClient)
    monkeypatch.setattr("app.config.settings.REMOTE_IMAGE_ALLOWED_HOSTS", "img.example")
    monkeypatch.setattr(
        "app.service.security.url_policy._resolve_addresses",
        lambda _hostname, _port: {"93.184.216.34"},
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        response = await client.get("/api/v1/miniapp/products/72001/image")

    assert response.status_code == 200
    assert response.content == b"\xff\xd8cake-image"
    assert response.headers["content-type"] == "image/jpeg"
    assert _FakeImageClient.requested_urls == [
        "https://img.example/proxy-strawberry.jpg"
    ]


@pytest.mark.asyncio
async def test_miniapp_product_image_proxy_rejects_missing_and_unsafe_images(
    db: aiosqlite.Connection,
    app: FastAPI,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """无图片、下架商品或非 http 图片地址不应被代理。"""
    await seed_miniapp_product(db, item_id=72002, title="无图蛋糕", image="")
    await seed_miniapp_product(
        db, item_id=72003, title="非法协议蛋糕", image="file:///etc/passwd"
    )
    _FakeImageClient.requested_urls = []
    monkeypatch.setattr("app.service.catalog.application.AsyncClient", _FakeImageClient)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver"
    ) as client:
        missing_response = await client.get("/api/v1/miniapp/products/missing/image")
        empty_response = await client.get("/api/v1/miniapp/products/72002/image")
        unsafe_response = await client.get("/api/v1/miniapp/products/72003/image")

    assert missing_response.status_code == 404
    assert empty_response.status_code == 404
    assert unsafe_response.status_code == 404
    assert _FakeImageClient.requested_urls == []
