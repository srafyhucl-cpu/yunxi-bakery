"""企微智能机器人商品查询过滤。"""

from typing import Any

from app.service.wecom.intelligent_bot_tool_response import DEFAULT_TOOL_LIMIT

PRODUCT_QUERY_NOISE_WORDS = (
    "帮我看看",
    "帮我查下",
    "帮我查一下",
    "看一下",
    "看下",
    "有没有",
    "还有没有",
    "还有哪些",
    "还够不够",
    "够不够",
    "还够",
    "库存不够",
    "库存",
    "价格",
    "查询",
    "查",
    "还有",
    "有货",
    "没货",
    "怎么推荐替代",
    "推荐替代",
    "怎么推荐",
    "怎么跟客户说",
    "怎么回复客户",
    "回复客户",
    "替代",
    "不够",
    "在售",
    "能不能买",
    "能买",
    "可卖",
    "推荐",
    "商品",
    "多少",
    "吗",
    "什么",
)
GENERIC_PRODUCT_QUERY_WORDS = ("蛋糕", "面包", "甜品", "点心", "可卖", "商品")
PRODUCT_QUERY_PUNCTUATION = " ，。！？?：:、"


def compact_product(product: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(product.get("id", "")),
        "title": str(product.get("title", "")),
        "priceFen": int(product.get("priceFen", 0) or 0),
        "stock": int(product.get("stock", 0) or 0),
        "categoryName": str(product.get("categoryName", "")),
        "soldText": str(product.get("soldText", "")),
        "tags": product.get("tags", []),
    }


def filter_products(products: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    compact_products = [compact_product(item) for item in products]
    clean_query = clean_product_query(query)
    if is_broad_product_query(query, clean_query):
        return filter_broad_products(compact_products, clean_query)
    matched = [
        item for item in compact_products if product_matches_query(item, clean_query)
    ]
    if matched:
        return matched
    specific_terms = product_specific_terms(clean_query)
    if not specific_terms:
        return []
    return [
        item
        for item in compact_products
        if product_matches_all_terms(item, specific_terms)
    ]


def is_broad_product_query(query: str, clean_query: str) -> bool:
    if clean_query in GENERIC_PRODUCT_QUERY_WORDS:
        return True
    return not clean_query and any(
        word in query for word in GENERIC_PRODUCT_QUERY_WORDS
    )


def filter_broad_products(
    compact_products: list[dict[str, Any]], clean_query: str
) -> list[dict[str, Any]]:
    if not clean_query:
        return compact_products
    matched = [
        item for item in compact_products if product_matches_query(item, clean_query)
    ]
    return matched if matched else compact_products[:DEFAULT_TOOL_LIMIT]


def product_matches_query(product: dict[str, Any], clean_query: str) -> bool:
    if not clean_query:
        return False
    return clean_query.lower() in product_search_text(product)


def product_matches_all_terms(product: dict[str, Any], terms: list[str]) -> bool:
    haystack = product_search_text(product)
    return all(term.lower() in haystack for term in terms)


def product_search_text(product: dict[str, Any]) -> str:
    return " ".join(
        [
            product["title"],
            product["categoryName"],
            " ".join(str(tag) for tag in product["tags"]),
        ]
    ).lower()


def clean_product_query(query: str) -> str:
    clean_query = query.strip()
    for word in PRODUCT_QUERY_NOISE_WORDS:
        clean_query = clean_query.replace(word, "")
    for char in PRODUCT_QUERY_PUNCTUATION:
        clean_query = clean_query.replace(char, " ")
    return clean_query.strip()


def product_specific_terms(clean_query: str) -> list[str]:
    specific_query = clean_query
    for word in GENERIC_PRODUCT_QUERY_WORDS:
        specific_query = specific_query.replace(word, " ")
    return [term for term in specific_query.split() if term]


def is_featured_query(query: str) -> bool:
    return "主推" in query or "精选" in query
