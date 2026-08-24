from app.service.wecom.intelligent_bot_product_filter import filter_products


def test_filter_products_ignores_employee_helper_words() -> None:
    products = [
        {
            "id": "1001",
            "title": "伯牙绝弦",
            "priceFen": 25800,
            "stock": 72,
            "categoryName": "生日蛋糕",
            "soldText": "",
            "tags": ["生日蛋糕"],
        }
    ]

    matched = filter_products(products, "帮我看看伯牙绝弦库存")

    assert [item["title"] for item in matched] == ["伯牙绝弦"]


def test_filter_products_ignores_replacement_and_reply_words() -> None:
    products = [
        {
            "id": "1001",
            "title": "伯牙绝弦",
            "priceFen": 25800,
            "stock": 72,
            "categoryName": "生日蛋糕",
            "soldText": "",
            "tags": ["生日蛋糕"],
        }
    ]

    replacement_matched = filter_products(products, "伯牙绝弦库存不够怎么推荐替代")
    reply_matched = filter_products(products, "伯牙绝弦没货怎么跟客户说")

    assert [item["title"] for item in replacement_matched] == ["伯牙绝弦"]
    assert [item["title"] for item in reply_matched] == ["伯牙绝弦"]
