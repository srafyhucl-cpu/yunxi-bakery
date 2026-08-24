"""RAG Document 规则 rerank 组件。"""

from typing import Any

RERANK_KEYWORDS = (
    "退款",
    "售后",
    "取消",
    "配送",
    "运费",
    "自提",
    "库存",
    "有货",
    "价格",
    "规格",
    "过敏",
    "成分",
    "人工",
)


def rerank_documents_by_query_rules(query: str, documents: list[Any]) -> list[Any]:
    """按客户 query 与 Document 的规则相关性稳定排序。"""
    scored_documents = [
        (_score_document(query, document), index, document)
        for index, document in enumerate(documents)
    ]
    scored_documents.sort(key=lambda item: (-item[0], item[1]))
    return [document for _score, _index, document in scored_documents]


def _score_document(query: str, document: Any) -> float:
    normalized_query = " ".join(query.split())
    title = str(getattr(document, "metadata", {}).get("title", ""))
    content = str(getattr(document, "page_content", ""))
    category = str(getattr(document, "metadata", {}).get("category", ""))
    score = 0.0

    if normalized_query and normalized_query in title:
        score += 6.0
    if normalized_query and normalized_query in content:
        score += 3.0

    for keyword in RERANK_KEYWORDS:
        if keyword not in normalized_query:
            continue
        if keyword in title:
            score += 4.0
        if keyword in content:
            score += 2.0
        if _category_matches_keyword(category, keyword):
            score += 1.0
    return score


def _category_matches_keyword(category: str, keyword: str) -> bool:
    if keyword in {"退款", "售后", "取消"}:
        return category in {"after_sales", "policy", "faq"}
    if keyword in {"配送", "运费", "自提"}:
        return category in {"delivery", "policy", "faq"}
    if keyword in {"库存", "有货", "价格", "规格"}:
        return category == "product"
    if keyword in {"过敏", "成分", "人工"}:
        return category in {"safety", "faq", "policy"}
    return False
