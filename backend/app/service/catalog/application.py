"""商品目录领域应用服务。"""

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from httpx import AsyncClient
from app.logger import setup_logger
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
from app.service.catalog.product_options import (
    ORDER_MODE_DIRECT,
    build_product_options,
)
from app.service.security.url_policy import fetch_limited_remote_image
from app.service.order.fulfillment_types import (
    FULFILLMENT_PREORDER_CAKE,
    classify_fulfillment_type,
)

DEFAULT_PRODUCT_LIMIT = 50
MAX_PRODUCT_LIMIT = 100
PRODUCT_SORT_POPULAR = "popular"
MAX_IDS_QUERY = 50


@dataclass(frozen=True)
class ProductPage:
    """商品列表分页读模型。"""

    items: list[dict]
    total: int
    limit: int
    offset: int

    @property
    def has_more(self) -> bool:
        return self.offset + self.limit < self.total

    def meta(self) -> dict:
        return {
            "total": self.total,
            "limit": self.limit,
            "offset": self.offset,
            "hasMore": self.has_more,
        }


IMAGE_FETCH_TIMEOUT_SECONDS = 8.0
MAX_IMAGE_BYTES = 5 * 1024 * 1024

logger = setup_logger()


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
        sort: str = "",
        limit: int = DEFAULT_PRODUCT_LIMIT,
        offset: int = 0,
        keyword: str = "",
    ) -> list[dict]:
        """兼容旧调用，只返回当前页商品数组。"""
        page = await self.list_products_page(
            ids=ids,
            category_id=category_id,
            featured=featured,
            sort=sort,
            limit=limit,
            offset=offset,
            keyword=keyword,
        )
        return page.items

    async def list_products_page(
        self,
        *,
        ids: str = "",
        category_id: str = "",
        featured: bool = False,
        sort: str = "",
        limit: int = DEFAULT_PRODUCT_LIMIT,
        offset: int = 0,
        keyword: str = "",
    ) -> ProductPage:
        """返回商品列表页及总数，支持关键词和服务端分页。"""
        page_limit, page_offset = self._normalize_product_pagination(limit, offset)
        normalized_keyword = keyword.strip()
        if ids.strip():
            items = await self._list_products_by_ids(ids)
            return ProductPage(
                items=items,
                total=len(items),
                limit=max(len(items), 1),
                offset=0,
            )

        featured_titles = await self._get_featured_titles(featured)
        sort_by = "soldNum" if sort == PRODUCT_SORT_POPULAR else ""
        if featured_titles is not None:
            total = await self._product_repo.count_products(
                search=normalized_keyword,
                is_active=1,
                featured_titles=featured_titles,
            )
            entries = await self._product_repo.get_all_products(
                search=normalized_keyword,
                limit=max(total, 1),
                offset=0,
                is_active=1,
                featured_titles=featured_titles,
                sort_by=sort_by,
            )
            entries = self._sort_entries_by_titles(entries, featured_titles)
            page_entries = entries[page_offset : page_offset + page_limit]
            return ProductPage(
                items=await self._serialize_entries(page_entries),
                total=total,
                limit=page_limit,
                offset=page_offset,
            )

        if category_id.startswith("youzan-") and self._youzan_product_repo is not None:
            category_key = parse_youzan_category_id(category_id)
            total = await self._youzan_product_repo.count_products_by_category_key(
                category_key,
                keyword=normalized_keyword,
            )
            entries = await self._list_entries_by_youzan_category(
                category_key,
                keyword=normalized_keyword,
                limit=page_limit,
                offset=page_offset,
                sort_by=sort_by,
            )
            return ProductPage(
                items=await self._serialize_entries(
                    entries, preferred_category_id=category_id
                ),
                total=total,
                limit=page_limit,
                offset=page_offset,
            )

        legacy_category = "" if category_id in ("", "all") else category_id
        total = await self._product_repo.count_products(
            search=normalized_keyword,
            is_active=1,
            category_search=legacy_category,
        )
        entries = await self._product_repo.get_all_products(
            search=normalized_keyword,
            category_search=legacy_category,
            limit=page_limit,
            offset=page_offset,
            is_active=1,
            sort_by=sort_by,
        )
        return ProductPage(
            items=await self._serialize_entries(entries),
            total=total,
            limit=page_limit,
            offset=page_offset,
        )

    async def list_categories(self) -> list[dict]:
        """返回公开商品分类。"""
        return await self._serializer.build_public_categories()

    async def get_product(self, product_id: str) -> dict | None:
        """读取商品详情，优先使用有赞商品 ID。"""
        entry = await self._get_product_entry(product_id)
        if entry is None:
            return None
        product = await self._serializer.serialize_product(entry)
        enriched = await self._with_product_options([product])
        return enriched[0]

    async def fetch_product_image(self, product_id: str) -> ProductImagePayload | None:
        """通过商品 ID 返回商品图：优先本地文件，未迁移时回源有赞。"""
        local_image = await self._local_image_payload(product_id)
        if local_image is not None:
            return local_image
        entry = await self._get_product_entry(product_id)
        if entry is None:
            return None

        image_url = str(getattr(entry, "image_url", "") or "").strip()
        hosts = settings.REMOTE_IMAGE_ALLOWED_HOSTS.split(",")
        if not self._is_remote_image_url(image_url):
            return None
        result = None
        try:
            result = await fetch_limited_remote_image(
                image_url,
                allowed_hosts=hosts,
                timeout_seconds=IMAGE_FETCH_TIMEOUT_SECONDS,
                max_bytes=MAX_IMAGE_BYTES,
                client_factory=AsyncClient,
            )
        except Exception:
            # 图片代理拉取失败必须留痕，降级为 404 而不是 500
            logger.error(
                "商品图片代理拉取异常 product_id=%s image_url=%s",
                product_id,
                image_url,
                exc_info=True,
            )
            return None
        if result is None:
            return None
        content, content_type = result
        if not content:
            return None
        return ProductImagePayload(content=content, content_type=content_type)

    async def _local_image_payload(self, product_id: str) -> ProductImagePayload | None:
        """读取已迁移到服务器的商品图；路径越界或文件缺失时回退远程。"""
        if self._youzan_product_repo is None:
            return None
        rows = await self._youzan_product_repo.get_option_rows([product_id])
        relative = str(
            (rows.get(str(product_id)) or {}).get("image_local") or ""
        ).strip()
        if not relative:
            return None
        base = Path(settings.DB_PATH).resolve().parent
        file_path = (base / relative).resolve()
        if base != file_path.parent and base not in file_path.parents:
            return None
        if not file_path.is_file():
            return None
        content = file_path.read_bytes()
        if not content or len(content) > MAX_IMAGE_BYTES:
            return None
        content_type = {
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(file_path.suffix.lower(), "image/jpeg")
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
        self,
        category_key: str,
        *,
        keyword: str = "",
        limit: int = DEFAULT_PRODUCT_LIMIT,
        offset: int = 0,
        sort_by: str = "",
    ) -> list[KnowledgeEntry]:
        if self._youzan_product_repo is None:
            return []
        products = await self._youzan_product_repo.list_products_by_category_key(
            category_key,
            keyword=keyword,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
        )
        entries: list[KnowledgeEntry] = []
        for product in products:
            entry = await self._get_entry_by_youzan_item_id(str(product["item_id"]))
            if entry is not None:
                entries.append(entry)
        return entries

    async def _serialize_entries(
        self,
        entries: list[KnowledgeEntry],
        *,
        preferred_category_id: str = "",
    ) -> list[dict]:
        products = [
            await self._serializer.serialize_product(
                entry, preferred_category_id=preferred_category_id
            )
            for entry in entries
        ]
        return await self._with_product_options(products)

    async def _with_product_options(self, products: list[dict]) -> list[dict]:
        """为商品读模型补上规格与选项，让前台按真实数据决定下单方式。

        有尺寸 SKU 或定制属性即提前预订；纯现货商品保持直接下单。
        没有有赞商品行时按直接下单处理，避免历史/异常数据把商品变成不可售。
        """
        if not products:
            return products
        rows: dict[str, dict] = {}
        if self._youzan_product_repo is not None:
            rows = await self._youzan_product_repo.get_option_rows(
                [str(product.get("id") or "") for product in products]
            )
        for product in products:
            row = rows.get(str(product.get("id") or ""))
            if row is None:
                product.update(
                    {"orderMode": ORDER_MODE_DIRECT, "variants": [], "options": []}
                )
                continue
            product.update(
                build_product_options(
                    str(row.get("skus_json") or ""),
                    str(row.get("item_props_json") or ""),
                    base_price_fen=int(row.get("price_fen") or 0),
                )
            )
            # 后台按商品覆盖履约方式：固定尺寸蛋糕等无规格数据的商品也能正确判为预订
            override = str(row.get("fulfillment_mode") or "").strip()
            if override in ("preorder", "direct"):
                product["orderMode"] = override
            elif product["orderMode"] == "direct" and self._is_preorder_title(
                str(product.get("title") or "")
            ):
                # 标题命中定制关键词的历史商品与下单判定保持一致，避免商品页说现货、下单却要预订
                product["orderMode"] = "preorder"
            # 图片已迁到服务器时优先走本地代理，避免有赞 CDN 停服后裂图
            if str(row.get("image_local") or "").strip():
                product["imageUrl"] = (
                    f"/api/v1/miniapp/products/{product.get('id')}/image"
                )
        return products

    @staticmethod
    def _is_preorder_title(title: str) -> bool:
        """标题命中定制关键词时按预订处理，与订单履约判定保持一致。"""
        return (
            classify_fulfillment_type({"title": title}, title)
            == FULFILLMENT_PREORDER_CAKE
        )

    def _normalize_product_pagination(self, limit: int, offset: int) -> tuple[int, int]:
        """限制公开列表分页范围，避免单请求拉取整库。"""
        normalized_limit = min(max(int(limit), 1), MAX_PRODUCT_LIMIT)
        normalized_offset = max(int(offset), 0)
        return normalized_limit, normalized_offset

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
