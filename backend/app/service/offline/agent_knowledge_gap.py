"""离线知识缺口挖掘 Agent。"""

import json
from dataclasses import dataclass
from functools import lru_cache

from app.exceptions import LLMError
from app.logger import setup_logger
from app.models.conversation_review import ConversationReview
from app.models.knowledge_gap import KnowledgeGap, KnowledgeGapCreate
from app.repository.knowledge_gap_repo import KnowledgeGapRepo
from app.repository.message_repo import MessageRepo
from app.service.agents.llm import get_langchain_chat_model
from app.service.offline.agent_shared import format_dialog
from app.service.offline.json_utils import parse_json_object
from app.service.offline.model_selection import select_offline_gap_model
from app.service.offline.quality_signals import GapSignal, extract_gap_signals
from app.service.privacy_redaction import redact_external_text


logger = setup_logger()

LOW_QUALITY_SCORE_THRESHOLD = 60

KNOWLEDGE_GAP_SYSTEM_PROMPT = (
    "你是芸熙烘焙知识库运营助手。请只输出 JSON："
    '{"question_norm": "归一化问题", "proposed_answer": "候选答案"}。'
    "只在知识库可能缺失时输出具体问题；如果没有明显缺口，question_norm 为空字符串。"
    "候选答案必须保守表达，等待人工审核，不要编造价格、库存或配送承诺。"
)


@lru_cache(maxsize=1)
def _get_knowledge_gap_prompt_template():
    """延迟构建知识缺口提示模板，避免模块导入阶段加载重依赖。"""
    from langchain_core.prompts import ChatPromptTemplate

    return ChatPromptTemplate.from_messages(
        [("system", "{system_prompt}"), ("user", "{user_content}")]
    )


@dataclass
class ParsedKnowledgeGap:
    """LLM 知识缺口输出。"""

    question_norm: str
    proposed_answer: str


class KnowledgeGapAgent:
    """基于低分质检会话生成待人工审核的知识缺口建议。"""

    def __init__(
        self,
        message_repo: MessageRepo,
        gap_repo: KnowledgeGapRepo,
        max_reviews: int = 50,
        reviewer_model: str = "",
    ) -> None:
        self._message_repo = message_repo
        self._gap_repo = gap_repo
        self._max_reviews = max_reviews
        self._reviewer_model = select_offline_gap_model(reviewer_model)
        self.last_run_result: list[KnowledgeGap] = []

    async def run(self, reviews: list[ConversationReview]) -> list[KnowledgeGap]:
        """从低分质检结果中挖掘知识缺口，单条失败不影响后续。"""
        gaps: list[KnowledgeGap] = []
        for review in reviews[: self._max_reviews]:
            if review.quality_score > LOW_QUALITY_SCORE_THRESHOLD:
                continue
            try:
                messages = await self._message_repo.get_by_session(review.session_id)
                if not messages:
                    continue
                parsed = await self._extract_gap(review, messages)
                gap_signals = _merge_gap_signals(parsed, extract_gap_signals(messages))
                for gap_signal in gap_signals:
                    gaps.append(
                        await self._gap_repo.upsert_open(
                            KnowledgeGapCreate(
                                question_norm=gap_signal.question_norm,
                                proposed_answer=gap_signal.proposed_answer,
                                related_sessions_json=json.dumps(
                                    [review.session_id],
                                    ensure_ascii=False,
                                ),
                            )
                        )
                    )
            except Exception as exc:
                logger.error(
                    "离线知识缺口挖掘失败 session=%s err=%s", review.session_id, exc
                )
        self.last_run_result = gaps
        return gaps

    async def _extract_gap(
        self,
        review: ConversationReview,
        messages: list,
    ) -> ParsedKnowledgeGap:
        content = await _invoke_gap_chain(
            model_name=self._reviewer_model,
            user_content=_build_gap_input(review, messages),
        )
        return _parse_gap_json(content)


async def _invoke_gap_chain(*, model_name: str, user_content: str) -> str:
    """通过统一 LangChain Runnable 生成知识缺口候选。"""
    provider = "mimo" if "mimo" in model_name.lower() else "deepseek"
    try:
        model = get_langchain_chat_model(
            provider=provider,
            model=model_name,
            temperature=0,
        ).bind(max_tokens=512)
        from langchain_core.output_parsers import StrOutputParser

        chain = _get_knowledge_gap_prompt_template() | model | StrOutputParser()
        return await chain.ainvoke(
            {
                "system_prompt": KNOWLEDGE_GAP_SYSTEM_PROMPT,
                "user_content": redact_external_text(user_content),
            }
        )
    except Exception as exc:
        raise LLMError("知识缺口 LLM 调用失败") from exc


def _build_gap_input(review: ConversationReview, messages: list) -> str:
    """组合质检问题与原始对话，供知识缺口 Agent 判断。"""
    return (
        f"质检分数：{review.quality_score}\n"
        f"质检问题：{review.issues_json}\n"
        f"会话内容：\n{format_dialog(messages)}"
    )


def _merge_gap_signals(
    parsed: ParsedKnowledgeGap,
    signal_gaps: list[GapSignal],
) -> list[GapSignal]:
    gaps = list(signal_gaps)
    if parsed.question_norm:
        gaps.insert(
            0,
            GapSignal(
                question_norm=parsed.question_norm,
                proposed_answer=parsed.proposed_answer,
            ),
        )
    return _unique_gap_signals(gaps)


def _unique_gap_signals(gaps: list[GapSignal]) -> list[GapSignal]:
    seen: set[str] = set()
    values: list[GapSignal] = []
    for gap in gaps:
        if gap.question_norm in seen:
            continue
        values.append(gap)
        seen.add(gap.question_norm)
    return values


def _parse_gap_json(content: str) -> ParsedKnowledgeGap:
    """解析知识缺口 JSON，格式不合规则按单条失败处理。"""
    try:
        payload = parse_json_object(content, "知识缺口结果不是有效 JSON")
    except LLMError as exc:
        raise LLMError("知识缺口结果不是有效 JSON") from exc
    question_norm = str(payload.get("question_norm", "")).strip()
    proposed_answer = str(payload.get("proposed_answer", "")).strip()
    return ParsedKnowledgeGap(
        question_norm=question_norm, proposed_answer=proposed_answer
    )
