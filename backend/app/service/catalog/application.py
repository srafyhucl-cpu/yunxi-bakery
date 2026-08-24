"""商品目录领域应用服务。"""

from dataclasses import dataclass
from urllib.parse import urlparse

from httpx import AsyncClient
from app.models.config import FEATURED_PRODUCTS_KEY
from app.config import settings
from app.models.knowledge import KnowledgeCategory, KnowledgeEntry
from app.repository.config_repo import ConfigRepo
from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.catalog.serialization import (
    CatalogProductSerializer,
    parse_youzan_category_id,
)
from app.service.security.url_policy import fetch_limited_remote_image

DEFAULT_PRODUCT_LIMIT = 50
MAX_IDS_QUERY = 50
IMAGE_FETCH_TIMEOUT_SECONDS = 8.0
MAX_IMAGE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True)
class ProductImagePayload:
    """商品图片代理返回体。"""

    content: bytes
    content_type: str


class CatalogApplicationService:
    """商品目录领域应用服务，承载公开商品读模型。"""

    def __init__(
        self,
        product_repo: KnowledgeProductRepo,
        knowledge_repo: KnowledgeRepo,
        config_repo: ConfigRepo,
        youzan_product_repo: YouzanProductRepo | None = None,
    ) -> None:
        self._product_repo = product_repo
        self._knowledge_repo = knowledge_repo
        self._config_repo = config_repo
        self._youzan_product_repo = youzan_product_repo
        self._serializer = CatalogProductSerializer(youzan_product_repo)

    async def list_products(
        self,
        *,
        ids: str = "",
        category_id: str = "",
        featured: bool = False,
    ) -> list[dict]:
        """按装修货架、分类或推荐位返回商品目录。"""
        if ids.strip():
            return await self._list_products_by_ids(ids)

        featured_titles = await self._get_featured_titles(featured)
        if category_id.startswith("youzan-") and self._youzan_product_repo is not None:
            entries = await self._list_entries_by_youzan_category(category_id)
            if entries:
                return [
                    await self._serializer.serialize_product(
                        entry, preferred_category_id=category_id
                    )
                    for entry in entries
                ]

        entries = await self._product_repo.get_all_products(
            search=category_id,
            limit=DEFAULT_PRODUCT_LIMIT,
            is_active=1,
            featured_titles=featured_titles,
        )
        if featured_titles is not None:
            entries = self._sort_entries_by_titles(entries, featured_titles)
        return [await self._serializer.serialize_product(entry) for entry in entries]

    async def list_categories(self) -> list[dict]:
        """返回公开商品分类。"""
        return await self._serializer.build_public_categories()

    async def get_product(self, product_id: str) -> dict | None:
        """读取商品详情，优先使用有赞商品 ID。"""
        entry = await self._get_product_entry(product_id)
        if entry is None:
            return None
        return await self._serializer.serialize_product(entry)

    async def fetch_product_image(self, product_id: str) -> ProductImagePayload | None:
        """通过商品 ID 受控拉取原始商品图。"""
        entry = await self._get_product_entry(product_id)
        if entry is None:
            return None

        image_url = str(getattr(entry, "image_url", "") or "").strip()
        hosts = settings.REMOTE_IMAGE_ALLOWED_HOSTS.split(",")
        if not self._is_remote_image_url(image_url):
            return None
        result = await fetch_limited_remote_image(
            image_url,
            allowed_hosts=hosts,
            timeout_seconds=IMAGE_FETCH_TIMEOUT_SECONDS,
            max_bytes=MAX_IMAGE_BYTES,
            client_factory=AsyncClient,
        )
        if result is None:
            return None
        content, content_type = result
        if not content:
            return None
        return ProductImagePayload(content=content, content_type=content_type)

    def _is_remote_image_url(self, image_url: str) -> bool:
        parsed = urlparse(image_url)
        return parsed.scheme in {"http", "https"} and bool(parsed.hostname)

    async def _list_products_by_ids(self, ids: str) -> list[dict]:
        products: list[dict] = []
        seen_ids: set[str] = set()
        product_ids = [item.strip() for item in ids.split(",") if item.strip()]
        for product_id in product_ids[:MAX_IDS_QUERY]:
            product = await self.get_product(product_id)
            if product is None or product["id"] in seen_ids:
                continue
            products.append(product)
            seen_ids.add(product["id"])
        return products

    async def _list_entries_by_youzan_category(
        self, category_id: str
    ) -> list[KnowledgeEntry]:
        if self._youzan_product_repo is None:
            return []
        category_key = parse_youzan_category_id(category_id)
        products = await self._youzan_product_repo.list_products_by_category_key(
            category_key,
            limit=DEFAULT_PRODUCT_LIMIT,
        )
        entries: list[KnowledgeEntry] = []
        for product in products:
            entry = await self._get_entry_by_youzan_item_id(str(product["item_id"]))
            if entry is not None:
                entries.append(entry)
        return entries

    async def _get_product_entry(self, product_id: str) -> KnowledgeEntry | None:
        normalized_id = product_id.strip()
        if not normalized_id:
            return None

        entry = await self._get_entry_by_youzan_item_id(normalized_id)
        if entry is not None:
            return entry

        if not normalized_id.isdigit():
            return None

        entry = await self._knowledge_repo.get_by_id(int(normalized_id))
        if not self._is_sellable_product_entry(entry):
            return None
        if entry.youzan_item_id:
            youzan_entry = await self._get_entry_by_youzan_item_id(entry.youzan_item_id)
            if youzan_entry is not None:
                return youzan_entry
        return entry

    async def _get_entry_by_youzan_item_id(
        self, product_id: str
    ) -> KnowledgeEntry | None:
        entries = await self._product_repo.get_all_products(
            limit=1,
            is_active=1,
            youzan_item_id_filter=product_id,
        )
        return entries[0] if entries else None

    async def _get_featured_titles(self, featured: bool) -> list[str] | None:
        if not featured:
            return None
        return await self._config_repo.get_list(FEATURED_PRODUCTS_KEY)

    def _is_sellable_product_entry(self, entry: KnowledgeEntry | None) -> bool:
        if entry is None:
            return False
        return entry.category == KnowledgeCategory.PRODUCT and bool(entry.is_active)

    def _sort_entries_by_titles(
        self,
        entries: list[KnowledgeEntry],
        ordered_titles: list[str],
    ) -> list[KnowledgeEntry]:
        """按后台主推配置顺序返回商品，缺失商品保持在末尾。"""
        order_map = {title: index for index, title in enumerate(ordered_titles)}
        return sorted(
            entries, key=lambda entry: order_map.get(entry.title, len(order_map))
        )


__all__ = ["CatalogApplicationService", "ProductImagePayload"]
