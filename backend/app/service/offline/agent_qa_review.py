"""离线会话质检 Agent。"""

import json
from dataclasses import dataclass
from functools import lru_cache

from app.config import settings
from app.exceptions import LLMError
from app.logger import setup_logger
from app.models.conversation_review import (
    ConversationReview,
    ConversationReviewCreate,
)
from app.models.message import Message
from app.repository.conversation_review_repo import ConversationReviewRepo
from app.repository.message_repo import MessageRepo
from app.repository.session_repo import SessionRepo
from app.service.agents.llm import get_langchain_chat_model
from app.service.offline.agent_shared import format_dialog
from app.service.offline.json_utils import parse_json_object
from app.service.offline.model_selection import select_offline_review_model
from app.service.offline.quality_signals import extract_review_issues
from app.service.privacy_redaction import redact_external_text


logger = setup_logger()

LOW_QUALITY_SCORE_THRESHOLD = 60
LOW_SCORE_EMPTY_ISSUE_FALLBACK = "模型给出低分但未说明具体问题，需人工复核"
QA_REVIEW_SYSTEM_PROMPT = (
    "你是芸熙烘焙客服质检员。请只输出 JSON："
    '{"quality_score": 0-100, "issues": ["问题1"]}。'
    "评分依据包括是否答准、是否答漏、态度是否友好、是否存在食品安全风险。"
    "如果分数低于 60，issues 必须说明具体问题；禁止输出 0 分但 issues 为空。"
)
QA_REVIEW_REPAIR_PROMPT = (
    "上一次质检输出不合格。请重新检查同一段对话，只输出合法 JSON："
    '{"quality_score": 0-100, "issues": ["具体问题"]}。'
)


@lru_cache(maxsize=1)
def _get_qa_review_prompt_template():
    """延迟构建质检提示模板，避免模块导入阶段加载重依赖。"""
    from langchain_core.prompts import ChatPromptTemplate

    return ChatPromptTemplate.from_messages(
        [("system", "{system_prompt}"), ("user", "{user_content}")]
    )


@dataclass
class ParsedQaReview:
    """LLM 质检输出的结构化结果。"""

    quality_score: int
    issues_json: str


class QaReviewAgent:
    """读取待质检会话，调用 LLM 后写入 conversation_reviews。"""

    def __init__(
        self,
        session_repo: SessionRepo,
        message_repo: MessageRepo,
        review_repo: ConversationReviewRepo,
        max_sessions: int = 200,
        reviewer_model: str = "",
    ) -> None:
        self._session_repo = session_repo
        self._message_repo = message_repo
        self._review_repo = review_repo
        self._max_sessions = max_sessions
        self._reviewer_model = select_offline_review_model(reviewer_model)
        self.last_run_result: list[ConversationReview] = []

    async def run(self) -> list[ConversationReview]:
        """执行一轮会话质检，单会话失败不影响后续会话。"""
        sessions = await self._session_repo.list_review_candidates(self._max_sessions)
        reviews: list[ConversationReview] = []
        for session in sessions:
            try:
                messages = await self._message_repo.get_by_session(session.id)
                if not messages:
                    continue
                parsed = await self._review_messages(messages)
                parsed = _merge_signal_issues(parsed, extract_review_issues(messages))
                reviews.append(
                    await self._review_repo.create(
                        ConversationReviewCreate(
                            session_id=session.id,
                            quality_score=parsed.quality_score,
                            issues_json=parsed.issues_json,
                            reviewer_model=self._reviewer_model,
                        )
                    )
                )
            except Exception as exc:
                logger.error("离线会话质检失败 session=%s err=%s", session.id, exc)
        self.last_run_result = reviews
        return reviews

    async def _review_messages(self, messages: list[Message]) -> ParsedQaReview:
        dialog = format_dialog(messages)
        last_content = ""
        max_attempts = settings.OFFLINE_LLM_REPAIR_RETRIES + 1
        for attempt in range(max_attempts):
            response = await _invoke_review_chain(
                model_name=self._reviewer_model,
                messages=_build_review_messages(dialog, last_content, attempt),
            )
            last_content = response or "{}"
            try:
                return _parse_review_json(last_content)
            except LLMError as exc:
                if attempt >= max_attempts - 1:
                    if str(exc) == "低分质检必须说明具体问题":
                        return ParsedQaReview(
                            quality_score=0,
                            issues_json=json.dumps(
                                [LOW_SCORE_EMPTY_ISSUE_FALLBACK],
                                ensure_ascii=False,
                            ),
                        )
                    raise
        raise LLMError("质检结果修复失败")


async def _invoke_review_chain(
    *,
    model_name: str,
    messages: list[dict[str, str]],
) -> str:
    """通过统一 LangChain Runnable 执行离线质检。"""
    provider = "mimo" if "mimo" in model_name.lower() else "deepseek"
    try:
        model = get_langchain_chat_model(
            provider=provider,
            model=model_name,
            temperature=0,
        ).bind(max_tokens=512)
        from langchain_core.output_parsers import StrOutputParser

        chain = _get_qa_review_prompt_template() | model | StrOutputParser()
        return await chain.ainvoke(
            {
                "system_prompt": messages[0]["content"],
                "user_content": redact_external_text(messages[1]["content"]),
            }
        )
    except Exception as exc:
        raise LLMError("离线质检 LLM 调用失败") from exc


def _build_review_messages(
    dialog: str,
    last_content: str,
    attempt: int,
) -> list[dict[str, str]]:
    if attempt == 0:
        return [
            {"role": "system", "content": QA_REVIEW_SYSTEM_PROMPT},
            {"role": "user", "content": dialog},
        ]
    return [
        {"role": "system", "content": QA_REVIEW_REPAIR_PROMPT},
        {
            "role": "user",
            "content": f"上一次输出：{last_content}\n\n对话内容：\n{dialog}",
        },
    ]


def _merge_signal_issues(
    parsed: ParsedQaReview,
    signal_issues: list[str],
) -> ParsedQaReview:
    if not signal_issues:
        return parsed
    issues = _load_issues(parsed.issues_json)
    for issue in signal_issues:
        if issue not in issues:
            issues.append(issue)
    score = min(parsed.quality_score, LOW_QUALITY_SCORE_THRESHOLD - 1)
    return ParsedQaReview(
        quality_score=score,
        issues_json=json.dumps(issues, ensure_ascii=False),
    )


def _load_issues(issues_json: str) -> list[str]:
    try:
        parsed = json.loads(issues_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(item) for item in parsed if str(item).strip()]


def _parse_review_json(content: str) -> ParsedQaReview:
    """解析质检 JSON，格式不合规则让调用方按单会话失败处理。"""
    try:
        payload = parse_json_object(content, "质检结果不是有效 JSON")
        raw_score = int(payload.get("quality_score", 0))
        issues = payload.get("issues", [])
    except (TypeError, ValueError, LLMError) as exc:
        raise LLMError("质检结果不是有效 JSON") from exc

    if not isinstance(issues, list):
        issues = []
    score = max(0, min(raw_score, 100))
    issues_text = [str(item) for item in issues if str(item).strip()]
    if score < LOW_QUALITY_SCORE_THRESHOLD and not issues_text:
        raise LLMError("低分质检必须说明具体问题")
    return ParsedQaReview(
        quality_score=score,
        issues_json=json.dumps(issues_text, ensure_ascii=False),
    )
