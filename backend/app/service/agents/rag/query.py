"""RAG 查询规划组件。"""

from dataclasses import dataclass


MAX_RAG_QUERY_VARIANTS = 3


@dataclass(frozen=True)
class RagQueryVariant:
    """单个 RAG 检索查询变体。"""

    query: str
    reason: str


@dataclass(frozen=True)
class RagQueryPlan:
    """RAG 检索查询计划。"""

    original_query: str
    variants: tuple[RagQueryVariant, ...]


def build_customer_rag_query_plan(query: str) -> RagQueryPlan:
    """为客户问题生成保守的检索查询变体。"""
    normalized_query = " ".join(query.split())
    if not normalized_query:
        return RagQueryPlan(original_query=query, variants=())

    variants = [RagQueryVariant(query=normalized_query, reason="original")]
    for expanded_query in _expand_customer_query(normalized_query):
        if len(variants) >= MAX_RAG_QUERY_VARIANTS:
            break
        if expanded_query == normalized_query:
            continue
        variants.append(RagQueryVariant(query=expanded_query, reason="rule_expand"))
    return RagQueryPlan(original_query=normalized_query, variants=tuple(variants))


def _expand_customer_query(query: str) -> tuple[str, ...]:
    if any(keyword in query for keyword in ("退款", "退货", "售后", "坏了")):
        return ("退款规则 售后政策", "售后处理 转人工")
    if any(keyword in query for keyword in ("配送", "送货", "快递", "运费")):
        return ("配送范围 配送费", "配送时间 自提")
    if any(keyword in query for keyword in ("库存", "还有", "有货", "卖完")):
        return ("商品库存 当前可售", "商品规格 价格")
    if any(keyword in query for keyword in ("价格", "多少钱", "规格", "口味")):
        return ("商品价格 规格 口味",)
    return ()
