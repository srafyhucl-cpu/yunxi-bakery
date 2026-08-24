import aiosqlite
import pytest

from app.repository.config_repo import ConfigRepo
from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.catalog import CatalogApplicationService
from tests.helpers.catalog_seed import seed_catalog_product


@pytest.fixture
def service(db: aiosqlite.Connection) -> CatalogApplicationService:
    return CatalogApplicationService(
        product_repo=KnowledgeProductRepo(db),
        knowledge_repo=KnowledgeRepo(db),
        config_repo=ConfigRepo(db),
        youzan_product_repo=YouzanProductRepo(db),
    )


async def test_list_categories_and_filter_by_item_base_classification(
    db: aiosqlite.Connection,
    service: CatalogApplicationService,
) -> None:
    await seed_catalog_product(
        db,
        item_id=66101,
        title="ITEM_INFO 分类蛋糕",
        classification_ids=["67"],
        updated_at="2026-06-16 10:00:00",
    )
    await YouzanProductRepo(db).upsert_category(
        tag_id="classification-67",
        title="有赞分类 67",
        sort=1000,
        product_count=1,
    )

    categories = await service.list_categories()
    products = await service.list_products(category_id="youzan-classification-67")

    assert {
        "id": "youzan-classification-67",
        "title": "有赞分类 67",
        "sort": 1000,
        "productCount": 1,
    } in categories
    assert [product["id"] for product in products] == ["66101"]
    assert products[0]["categoryId"] == "youzan-classification-67"
    assert products[0]["categoryName"] == "有赞分类 67"
