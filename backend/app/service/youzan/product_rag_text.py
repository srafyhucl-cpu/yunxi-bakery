"""有赞商品 RAG 文本构造工具。"""

import json
from urllib.parse import quote as url_quote

from app.logger import setup_logger
from app.service.youzan.client import YOUZAN_GOODS_H5_BASE_URL

logger = setup_logger()

FALLBACK_PRODUCT_DESC = (
    "精品烘焙推荐，新西兰进口动物奶油调配，不含防腐剂。建议0-4℃冷藏并于3天内食用完毕。"
)


def build_product_rag_content(
    title: str,
    alias: str,
    status_lbl: str,
    skus: list,
    item_props: list,
    price_fen: int,
    stock: int,
    desc_clean: str,
    tags_str: str,
    item_id: int = 0,
    image: str = "",
) -> str:
    """构建面向 LLM 上下文的商品 RAG 内容，保留展示所需库存明细。"""
    skus_text = _build_skus_text(skus, price_fen, stock, include_stock=True)
    props_text = _build_props_text(item_props)
    detail_url = f"{YOUZAN_GOODS_H5_BASE_URL}?alias={alias}"
    return (
        f"商品名称：{title}\n"
        f"在售状态：{status_lbl}\n"
        f"商品规格及秒级实时库存明细：\n{skus_text}\n\n"
        f"可定制口味、蛋糕胚、夹心及甜度选项（SPU 自定义属性）：\n{props_text}\n\n"
        f"商品特征与配方属性标签：{tags_str}\n"
        f"直购下单链接：{detail_url}\n"
        f"原料配方、保质期及夹心介绍：\n{desc_clean or FALLBACK_PRODUCT_DESC}"
        + _build_ump_line(title, alias, item_id, image, skus, price_fen)
    )


def build_product_embedding_text(
    title: str,
    alias: str,
    status_lbl: str,
    skus: list,
    item_props: list,
    price_fen: int,
    desc_clean: str,
    tags_str: str,
) -> str:
    """构建商品向量化文本，只保留稳定语义，不写入实时库存数字。"""
    skus_text = _build_skus_text(skus, price_fen, 0, include_stock=False)
    props_text = _build_props_text(item_props)
    detail_url = f"{YOUZAN_GOODS_H5_BASE_URL}?alias={alias}"
    return (
        f"商品名称：{title}\n"
        f"在售状态：{status_lbl}\n"
        f"商品规格与价格信息：\n{skus_text}\n\n"
        f"可定制口味、蛋糕胚、夹心及甜度选项（SPU 自定义属性）：\n{props_text}\n\n"
        f"商品特征与配方属性标签：{tags_str}\n"
        f"直购下单链接：{detail_url}\n"
        f"原料配方、保质期及夹心介绍：\n{desc_clean or FALLBACK_PRODUCT_DESC}"
    )


def _build_skus_text(
    skus: list, price_fen: int, stock: int, *, include_stock: bool
) -> str:
    sku_lines: list[str] = []
    for sku in skus:
        price_yuan = sku.get("price", price_fen) / 100.0
        prop_desc = _sku_prop_desc(sku)
        stock_suffix = (
            f"，当前可用库存 {sku.get('quantity', 0)} 件" if include_stock else ""
        )
        sku_lines.append(
            f"- 规格型号【{prop_desc}】：售价 ￥{price_yuan:.2f} 元{stock_suffix}"
        )
    if sku_lines:
        return "\n".join(sku_lines)
    stock_suffix = f"，当前可用总库存 {stock} 件" if include_stock else ""
    return f"- 规格：单售价 ￥{price_fen / 100.0:.2f} 元{stock_suffix}"


def _sku_prop_desc(sku: dict) -> str:
    prop_json = sku.get("properties_name_json", "")
    if not prop_json:
        return "标准规格"
    try:
        props = json.loads(prop_json)
        return " | ".join(f"{p.get('k')}:{p.get('v')}" for p in props)
    except Exception as exc:
        logger.warning("解析 SKU 属性失败: %s", exc)
        return "标准规格"


def _build_props_text(item_props: list) -> str:
    prop_lines: list[str] = []
    for prop in item_props:
        p_name = prop.get("prop_name", "")
        is_mult = " (允许多选)" if prop.get("is_multiple") else " (单选)"
        options = []
        for model in prop.get("text_models", []):
            opt_val = model.get("prop_text_name", "")
            opt_price = model.get("price", 0) / 100.0
            opt_price_desc = f" (加价: +￥{opt_price:.2f}元)" if opt_price > 0 else ""
            options.append(f"{opt_val}{opt_price_desc}")
        prop_lines.append(f"- 【{p_name}】{is_mult}：{'、'.join(options)}")
    return "\n".join(prop_lines) if prop_lines else "- 定制加料选项：暂无特殊定制属性"


def _build_ump_line(
    title: str,
    alias: str,
    item_id: int,
    image: str,
    skus: list,
    price_fen: int,
) -> str:
    if not item_id or not image or not alias:
        return ""
    min_price_fen = min(
        (sku.get("price", price_fen) for sku in skus), default=price_fen
    )
    price_str = f"{min_price_fen / 100:.2f}"
    detail_url = f"{YOUZAN_GOODS_H5_BASE_URL}?alias={alias}"
    return (
        f"\n[UMP: type=card&id={item_id}&title={url_quote(title)}"
        f"&price={price_str}&src={url_quote(image)}&url={url_quote(detail_url)}]"
    )
