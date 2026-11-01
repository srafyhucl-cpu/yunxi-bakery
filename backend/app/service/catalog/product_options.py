"""商品规格与定制选项读模型。

有赞后台把「尺寸/口味/包装」放在 SKU，把「蛋糕胚/夹心/甜度」放在商品属性。
这里统一转换成前台可选项目，让小程序按商品真实数据决定下单方式，
而不是再按标题关键词猜：有规格或属性就是提前预订，没有就是现货。
"""

from __future__ import annotations

import json
from typing import Any

SIZE_PROPERTY_NAME = "尺寸"
ORDER_MODE_DIRECT = "direct"
ORDER_MODE_PREORDER = "preorder"


def build_product_options(
    skus_json: str,
    item_props_json: str,
    *,
    base_price_fen: int,
) -> dict[str, Any]:
    """把有赞 SKU 与商品属性转换成前台规格/选项读模型。

    只有「按尺寸定制」或「带蛋糕胚/夹心/甜度属性」才算提前预订；
    数字蜡烛、曲奇口味、礼盒包装这类规格仍是现货，只是要选具体规格。
    """
    variants = _parse_variants(skus_json, base_price_fen)
    options = _parse_options(item_props_json)
    has_size = any(item["property"] == SIZE_PROPERTY_NAME for item in variants)
    is_preorder = has_size or bool(options)
    return {
        "orderMode": ORDER_MODE_PREORDER if is_preorder else ORDER_MODE_DIRECT,
        "variants": variants,
        "options": options,
    }


def _parse_variants(skus_json: str, base_price_fen: int) -> list[dict[str, Any]]:
    """解析 SKU：尺寸优先，其余（口味/数字/包装）按同一规格组处理。"""
    variants: list[dict[str, Any]] = []
    for sku in _loads_list(skus_json):
        if not isinstance(sku, dict):
            continue
        name = ""
        property_name = ""
        for prop in _loads_list(sku.get("properties_name_json")):
            if not isinstance(prop, dict):
                continue
            value = str(prop.get("v") or "").strip()
            if not value:
                continue
            name = value
            property_name = str(prop.get("k") or "").strip()
            if property_name == SIZE_PROPERTY_NAME:
                break
        if not name:
            continue
        variants.append(
            {
                "id": str(sku.get("sku_id") or ""),
                "property": property_name or SIZE_PROPERTY_NAME,
                "name": name,
                "priceFen": int(sku.get("price") or base_price_fen),
                "stock": int(sku.get("quantity") or 0),
            }
        )
    variants.sort(key=lambda item: item["priceFen"])
    return variants


def _parse_options(item_props_json: str) -> list[dict[str, Any]]:
    """解析商品属性：每个属性是一组单选/多选，选项自带加价。"""
    options: list[dict[str, Any]] = []
    for prop in _loads_list(item_props_json):
        if not isinstance(prop, dict):
            continue
        name = str(prop.get("prop_name") or "").strip()
        choices = [
            {
                "id": str(model.get("prop_text_id") or ""),
                "name": str(model.get("prop_text_name") or "").strip(),
                "priceDeltaFen": int(model.get("price") or 0),
            }
            for model in _loads_list(prop.get("text_models"))
            if isinstance(model, dict)
            and str(model.get("prop_text_name") or "").strip()
        ]
        if not name or not choices:
            continue
        options.append(
            {
                "name": name,
                "required": bool(prop.get("is_necessary")),
                "multiple": bool(prop.get("is_multiple")),
                "choices": choices,
            }
        )
    return options


def _loads_list(raw: Any) -> list[Any]:
    """容错解析有赞 JSON 字段：脏数据按空列表处理，不影响商品可售。"""
    if isinstance(raw, list):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


__all__ = [
    "ORDER_MODE_DIRECT",
    "ORDER_MODE_PREORDER",
    "SIZE_PROPERTY_NAME",
    "build_product_options",
]
