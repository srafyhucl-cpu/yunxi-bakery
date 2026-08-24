from app.service.wecom.ump import parse_ump_tags


def test_parse_ump_tags_removes_tags_and_decodes_params() -> None:
    text = (
        "推荐这款 [UMP: type=card&title=%E6%8A%B9%E8%8C%B6&price=28] "
        "也可以看看 [UMP: type=image&src=https%3A%2F%2Fexample.com%2Fa.jpg]"
    )

    clean_text, tags = parse_ump_tags(text)

    assert clean_text == "推荐这款  也可以看看"
    assert tags == [
        {"type": "card", "title": "抹茶", "price": "28"},
        {"type": "image", "src": "https://example.com/a.jpg"},
    ]


def test_parse_ump_tags_ignores_pairs_without_equals() -> None:
    clean_text, tags = parse_ump_tags("文字 [UMP: bad&type=card&title=蛋糕]")

    assert clean_text == "文字"
    assert tags == [{"type": "card", "title": "蛋糕"}]
