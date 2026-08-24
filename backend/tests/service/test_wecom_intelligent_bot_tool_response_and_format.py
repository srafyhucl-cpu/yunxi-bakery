from app.service.wecom.intelligent_bot_tool_format import filter_products
from app.service.wecom.intelligent_bot_tool_response import ok_response, tool_error


def test_ok_response_exposes_readable_result_text() -> None:
    products_text = "草莓蛋糕｜268.00元｜库存 6｜生日蛋糕"

    payload = ok_response(
        "product_lookup",
        "草莓蛋糕",
        "找到 1 个可展示商品。",
        productsText=products_text,
        nextAction="库存和价格以小程序商品数据为准。",
    )

    assert payload["suggestedReply"] == products_text
    assert payload["result"] == products_text
    assert payload["resultText"] == products_text


def test_tool_error_exposes_readable_result_text() -> None:
    payload = tool_error("product_lookup", "商品查询失败", "请稍后重试。")

    assert payload["suggestedReply"] == "商品查询失败"
    assert payload["result"] == "商品查询失败"
    assert payload["resultText"] == "商品查询失败"


def test_filter_products_does_not_fallback_for_specific_unmatched_query() -> None:
    products = [
        {
            "id": "71001",
            "title": "杨枝甘露生日蛋糕",
            "priceFen": 27800,
            "stock": 10,
            "categoryName": "生日蛋糕",
            "tags": ["芒果"],
        },
        {
            "id": "71002",
            "title": "纯巧克力千层",
            "priceFen": 26800,
            "stock": 8,
            "categoryName": "甜品",
            "tags": ["巧克力"],
        },
    ]

    assert filter_products(products, "草莓蛋糕") == []


def test_filter_products_uses_specific_modifier_after_generic_word() -> None:
    products = [
        {
            "id": "71001",
            "title": "草莓奶油杯",
            "priceFen": 3800,
            "stock": 12,
            "categoryName": "甜品",
            "tags": ["草莓"],
        },
        {
            "id": "71002",
            "title": "纯巧克力千层",
            "priceFen": 26800,
            "stock": 8,
            "categoryName": "甜品",
            "tags": ["巧克力"],
        },
    ]

    matched = filter_products(products, "草莓蛋糕")

    assert [item["title"] for item in matched] == ["草莓奶油杯"]


def test_filter_products_keeps_broad_category_queries_useful() -> None:
    products = [
        {
            "id": "71001",
            "title": "杨枝甘露生日蛋糕",
            "priceFen": 27800,
            "stock": 10,
            "categoryName": "生日蛋糕",
            "tags": ["芒果"],
        },
        {
            "id": "71002",
            "title": "100分面包",
            "priceFen": 1200,
            "stock": 20,
            "categoryName": "面包",
            "tags": ["早餐"],
        },
    ]

    matched = filter_products(products, "蛋糕")

    assert [item["title"] for item in matched] == ["杨枝甘露生日蛋糕"]
