from __future__ import annotations

from typing import Any

from app.logger import setup_logger

logger = setup_logger()

BM25_STOPWORDS = {
    "的",
    "了",
    "呢",
    "吗",
    "嘛",
    "么",
    "啊",
    "呀",
    "可以",
    "能",
    "能否",
    "是否",
    "有没有",
    "有",
    "没有",
    "怎么",
    "怎样",
    "如何",
    "多少",
    "几个",
    "哪些",
    "什么",
    "一下",
    "一个",
    "你们",
    "我们",
    "这边",
}
CHINESE_CHAR_START = "\u4e00"
CHINESE_CHAR_END = "\u9fff"
BM25_EXPAND_CHARS = {"退"}

try:
    import jieba
    from rank_bm25 import BM25Okapi
except ImportError as exc:
    jieba = None
    BM25Okapi = None
    BM25_IMPORT_ERROR = exc
else:
    BM25_IMPORT_ERROR = None


class BM25Searcher:
    """基于 jieba + BM25Okapi 的中文关键词检索器。"""

    def __init__(self) -> None:
        self._bm25: Any | None = None
        self._doc_keys: list[str] = []
        self._ready = False

    @property
    def doc_count(self) -> int:
        return len(self._doc_keys)

    def build(self, documents: list[tuple[str, str, str]]) -> None:
        """从知识库文档构建内存 BM25 索引。"""
        if BM25_IMPORT_ERROR is not None or jieba is None or BM25Okapi is None:
            logger.warning("BM25 依赖未安装，混合检索将自动降级: %s", BM25_IMPORT_ERROR)
            self._ready = False
            return

        tokenized_corpus: list[list[str]] = []
        self._doc_keys = []
        for doc_key, title, content in documents:
            tokens = self._tokenize(f"{title} {content}")
            if not tokens:
                continue
            self._doc_keys.append(str(doc_key))
            tokenized_corpus.append(tokens)

        if not tokenized_corpus:
            self._bm25 = None
            self._ready = False
            return

        self._bm25 = BM25Okapi(tokenized_corpus)
        self._ready = True
        logger.info("BM25 索引构建完成: %d 条", len(self._doc_keys))

    def search(self, query: str, limit: int = 8) -> list[tuple[str, float]]:
        """按 BM25 分数检索文档。"""
        if not self._ready or self._bm25 is None or limit <= 0:
            return []

        query_tokens = self._tokenize(query)
        if not query_tokens:
            return []

        scores = self._bm25.get_scores(query_tokens)
        ranked_indices = sorted(
            range(len(scores)),
            key=lambda idx: float(scores[idx]),
            reverse=True,
        )
        results: list[tuple[str, float]] = []
        for index in ranked_indices:
            score = float(scores[index])
            if score <= 0:
                break
            results.append((self._doc_keys[index], score))
            if len(results) >= limit:
                break
        return results

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        if jieba is None:
            return []
        tokens: list[str] = []
        seen: set[str] = set()
        for raw_token in jieba.lcut(text):
            token = raw_token.strip().lower()
            if not token or token in BM25_STOPWORDS:
                continue
            if token not in seen:
                tokens.append(token)
                seen.add(token)
            for char in token:
                if (
                    CHINESE_CHAR_START <= char <= CHINESE_CHAR_END
                    and char in BM25_EXPAND_CHARS
                    and char not in BM25_STOPWORDS
                    and char not in seen
                ):
                    tokens.append(char)
                    seen.add(char)
        return tokens
