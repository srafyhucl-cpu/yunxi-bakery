from app.service.bm25_search import BM25Searcher


def test_bm25_search_finds_exact_chinese_terms() -> None:
    searcher = BM25Searcher()
    searcher.build(
        [
            ("cake", "提拉米苏蛋糕", "咖啡和马斯卡彭风味"),
            ("bread", "吐司面包", "柔软奶香"),
            ("cookie", "黄油曲奇", "酥脆点心"),
        ]
    )

    assert searcher.search("提拉米苏多少钱", limit=1)[0][0] == "cake"


def test_bm25_search_returns_empty_before_build() -> None:
    searcher = BM25Searcher()

    assert searcher.search("提拉米苏") == []
