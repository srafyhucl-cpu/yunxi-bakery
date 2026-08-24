"""有赞商品事件的属性与成分解析。"""

import json

from app.logger import setup_logger

logger = setup_logger()

SPECIAL_INGREDIENTS = [
    "蜜红豆",
    "抹茶",
    "草莓",
    "芒果",
    "提拉米苏",
    "巧克力",
    "动物奶油",
    "夹心",
    "千层",
    "乳酪",
    "芝士",
    "冷藏",
    "保质期",
]


def extract_item_tags(
    title: str, skus: list, item_props: list, desc_clean: str
) -> tuple[list, list, list]:
    """从 SKU、属性配置和描述中提取检索标签。"""
    spec_names: list[str] = []
    for sku in skus:
        prop_json = sku.get("properties_name_json", "")
        if prop_json:
            try:
                props = json.loads(prop_json)
                spec_names.extend(p.get("v", "") for p in props if p.get("v", ""))
            except Exception as exc:
                logger.warning("解析商品规格失败: %s", exc)

    prop_names: list[str] = []
    for prop in item_props:
        if prop.get("prop_name", ""):
            prop_names.append(prop["prop_name"])
        for model in prop.get("text_models", []):
            if model.get("prop_text_name", ""):
                prop_names.append(model["prop_text_name"])

    ingredients = [
        ingredient
        for ingredient in SPECIAL_INGREDIENTS
        if ingredient in desc_clean or ingredient in title
    ]
    return spec_names, prop_names, ingredients
