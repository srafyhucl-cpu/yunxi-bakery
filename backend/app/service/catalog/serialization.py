"""商品目录序列化与分类解析。"""

import json

from app.models.knowledge import KnowledgeEntry
from app.repository.youzan_repo import YouzanProductRepo

FALLBACK_CATEGORY_ID = "youzan-products"
FALLBACK_CATEGORY_TITLE = "有赞同步商品"
DEFAULT_PRODUCT_NOTICE = "手工现制商品，请下单前确认取货或配送时间。"
IMAGE_PROXY_PATH_TEMPLATE = "/api/v1/miniapp/products/{product_id}/image"
GENERIC_CATEGORY_TOKENS = frozenset({"商品", "价格", "推荐", "在售"})
RAW_CATEGORY_ID_PREFIXES = (
    "youzan-",
    "classification-",
    "group-",
    "second-group-",
    "leaf-category-",
)


class CatalogProductSerializer:
    """负责把商品知识条目转换为前台读模型。"""

    def __init__(self, youzan_product_repo: YouzanProductRepo | None = None) -> None:
        self._youzan_product_repo = youzan_product_repo

    async def serialize_product(
        self,
        entry: KnowledgeEntry,
        *,
        preferred_category_id: str = "",
    ) -> dict:
        """序列化单个商品条目。"""
        tags = split_tags(entry.keywords)
        sold_num = int(getattr(entry, "sold_num", 0) or 0)
        stock = int(getattr(entry, "stock", 0) or 0)
        category = await self._get_entry_category(entry, tags, preferred_category_id)
        return {
            "id": str(entry.youzan_item_id or entry.id),
            "title": entry.title,
            "subtitle": build_subtitle(entry.content),
            "imageUrl": build_image_proxy_url(entry),
            "priceFen": int(getattr(entry, "price_fen", 0) or 0),
            "soldText": build_sold_text(sold_num, stock),
            "categoryId": category["id"],
            "categoryName": category["title"],
            "stock": stock,
            "isActive": bool(entry.is_active),
            "tags": tags,
            "description": entry.content,
            "specs": tags,
            "notices": [DEFAULT_PRODUCT_NOTICE],
        }

    async def build_public_categories(self) -> list[dict]:
        """构建公开分类列表。"""
        if self._youzan_product_repo is None:
            return []
        categories = await self._youzan_product_repo.list_public_categories()
        return [
            {
                "id": build_youzan_category_id(str(category["tag_id"])),
                "title": category["title"],
                "sort": int(category["sort"] or 0),
                "productCount": int(category["product_count"] or 0),
            }
            for category in categories
        ]

    async def _get_entry_category(
        self,
        entry: KnowledgeEntry,
        tags: list[str],
        preferred_category_id: str = "",
    ) -> dict:
        classification_category = await self._resolve_classification_category(
            entry,
            preferred_category_id,
        )
        if classification_category is not None:
            return classification_category
        tag_category = await self._resolve_tag_category(
            entry, tags, preferred_category_id
        )
        if tag_category is not None:
            return tag_category
        return infer_category(tags)

    async def _resolve_classification_category(
        self,
        entry: KnowledgeEntry,
        preferred_category_id: str,
    ) -> dict | None:
        if self._youzan_product_repo is None:
            return None
        classification_ids = extract_json_ids(entry, "classification_ids_json")
        if not classification_ids:
            return None
        preferred_key = parse_youzan_category_id(preferred_category_id)
        preferred_classification_id = preferred_key.replace("classification-", "", 1)
        ordered_ids = (
            [preferred_classification_id]
            if preferred_classification_id in classification_ids
            else []
        )
        ordered_ids.extend(
            item for item in classification_ids if item not in ordered_ids
        )
        for classification_id in ordered_ids:
            category_key = f"classification-{classification_id}"
            category = await self._youzan_product_repo.get_category(category_key)
            if category is not None and int(category.get("is_public", 0) or 0) == 1:
                return {
                    "id": build_youzan_category_id(category_key),
                    "title": str(category["title"]),
                }
        return None

    async def _resolve_tag_category(
        self,
        entry: KnowledgeEntry,
        tags: list[str],
        preferred_category_id: str,
    ) -> dict | None:
        if self._youzan_product_repo is None:
            return None
        tag_ids = extract_json_ids(entry, "tag_ids_json")
        if not tag_ids:
            return None
        preferred_tag_id = preferred_category_id.replace("youzan-tag-", "", 1)
        ordered_tag_ids = [preferred_tag_id] if preferred_tag_id in tag_ids else []
        ordered_tag_ids.extend(
            tag_id for tag_id in tag_ids if tag_id not in ordered_tag_ids
        )
        for candidate_tag_id in ordered_tag_ids:
            category = await self._youzan_product_repo.get_category(candidate_tag_id)
            if category is not None and int(category.get("is_public", 0) or 0) == 1:
                return {
                    "id": build_youzan_category_id(str(category["tag_id"])),
                    "title": str(category["title"]),
                }
        if ordered_tag_ids:
            return infer_category(tags)
        return None


def build_subtitle(content: str) -> str:
    """生成卡片副标题。"""
    compact_content = " ".join((content or "").split())
    if len(compact_content) <= 36:
        return compact_content
    return f"{compact_content[:36]}..."


def build_sold_text(sold_num: int, stock: int) -> str:
    """生成销量文案。"""
    if sold_num > 0:
        return f"已售 {sold_num}"
    if stock > 0:
        return "库存充足"
    return "可咨询客服"


def infer_category(tags: list[str]) -> dict:
    """推导兜底分类。"""
    for tag in tags:
        normalized_tag = tag.strip()
        if is_specific_category_token(normalized_tag):
            return {"id": normalized_tag, "title": normalized_tag}
    return {"id": FALLBACK_CATEGORY_ID, "title": FALLBACK_CATEGORY_TITLE}


def is_specific_category_token(tag: str) -> bool:
    """判断标签是否适合作为前台分类。"""
    if not tag:
        return False
    if tag in GENERIC_CATEGORY_TOKENS:
        return False
    if tag.isdigit():
        return False
    return not any(tag.startswith(prefix) for prefix in RAW_CATEGORY_ID_PREFIXES)


def build_youzan_category_id(tag_id: str) -> str:
    """把有赞分类键转换为前台分类 ID。"""
    if tag_id.startswith("classification-"):
        return tag_id.replace("classification-", "youzan-classification-", 1)
    if tag_id.startswith("group-"):
        return tag_id.replace("group-", "youzan-group-", 1)
    if tag_id.startswith("second-group-"):
        return tag_id.replace("second-group-", "youzan-second-group-", 1)
    if tag_id.startswith("leaf-category-"):
        return tag_id.replace("leaf-category-", "youzan-leaf-category-", 1)
    return f"youzan-tag-{tag_id}"


def parse_youzan_category_id(category_id: str) -> str:
    """把前台分类 ID 转回有赞分类键。"""
    if category_id.startswith("youzan-classification-"):
        return category_id.replace("youzan-classification-", "classification-", 1)
    if category_id.startswith("youzan-group-"):
        return category_id.replace("youzan-group-", "group-", 1)
    if category_id.startswith("youzan-second-group-"):
        return category_id.replace("youzan-second-group-", "second-group-", 1)
    if category_id.startswith("youzan-leaf-category-"):
        return category_id.replace("youzan-leaf-category-", "leaf-category-", 1)
    return category_id.replace("youzan-tag-", "", 1)


def split_tags(keywords: str) -> list[str]:
    """拆分商品标签。"""
    normalized = keywords.replace("，", ",").replace("、", ",").replace(" ", ",")
    return [item.strip() for item in normalized.split(",") if item.strip()]


def build_image_proxy_url(entry: KnowledgeEntry) -> str:
    """生成图片代理地址。"""
    if not str(getattr(entry, "image_url", "") or "").strip():
        return ""
    product_id = str(entry.youzan_item_id or entry.id)
    return IMAGE_PROXY_PATH_TEMPLATE.format(product_id=product_id)


def extract_json_ids(entry: KnowledgeEntry, attr_name: str) -> list[str]:
    """从知识条目 JSON 字段中提取 ID 列表。"""
    raw_value = str(getattr(entry, attr_name, "") or "[]")
    try:
        value = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


__all__ = [
    "CatalogProductSerializer",
    "build_image_proxy_url",
]
