"""企微员工助手回调语义验收规则。"""

from __future__ import annotations

from dataclasses import dataclass
import re

PLAIN_TEXT_FORBIDDEN_MARKERS = ("**", "__", "`")
BLOCKQUOTE_MARK_PATTERN = re.compile(r"(?m)^>\s*")
EMPTY_RESULT_MARKERS = ("没有查到", "未查到", "暂无匹配", "暂无")
HANDOFF_MARKERS = ("转人工", "人工客服", "人工接手", "人工核对")


@dataclass(frozen=True)
class CallbackSemanticRule:
    """单个回调探针的语义约束。"""

    required_any_terms: tuple[str, ...] = ()
    required_all_terms: tuple[str, ...] = ()
    required_all_term_groups: tuple[tuple[str, ...], ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    allow_empty_result: bool = False
    allow_handoff: bool = False


def is_semantic_safe(content: str, rule: CallbackSemanticRule) -> bool:
    """判断回复是否满足探针语义约束。"""
    if rule.allow_handoff and has_handoff_result(content):
        return not any(term in content for term in rule.forbidden_terms)
    if rule.allow_empty_result and has_controlled_empty_result(content):
        return not any(term in content for term in rule.forbidden_terms)
    if rule.required_any_terms and not any(
        term in content for term in rule.required_any_terms
    ):
        return False
    if rule.required_all_terms and not all(
        term in content for term in rule.required_all_terms
    ):
        return False
    if rule.required_all_term_groups and not any(
        all(term in content for term in term_group)
        for term_group in rule.required_all_term_groups
    ):
        return False
    return not any(term in content for term in rule.forbidden_terms)


def has_controlled_empty_result(content: str) -> bool:
    """判断回复是否是明确的受控空结果。"""
    return any(marker in content for marker in EMPTY_RESULT_MARKERS)


def has_handoff_result(content: str) -> bool:
    """判断回复是否明确进入人工核对路径。"""
    return any(marker in content for marker in HANDOFF_MARKERS)


def has_plain_text_violation(content: str) -> bool:
    """企微员工助手 stream 回复必须是纯文本，不保留 Markdown 装饰。"""
    return any(marker in content for marker in PLAIN_TEXT_FORBIDDEN_MARKERS) or bool(
        BLOCKQUOTE_MARK_PATTERN.search(content)
    )
