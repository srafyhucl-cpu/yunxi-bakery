"""企微员工助手商品问法谓词。"""

from __future__ import annotations


PRODUCT_KNOWLEDGE_FOLLOWUP_KEYWORDS = (
    "怎么推荐",
    "推荐替代",
    "替代",
    "怎么跟客户说",
    "怎么回复客户",
    "回复客户",
    "话术",
)


def looks_like_product_knowledge_query(query: str) -> bool:
    """判断是否需要在商品实时数据后补充知识库话术。"""
    return any(word in query for word in PRODUCT_KNOWLEDGE_FOLLOWUP_KEYWORDS)
