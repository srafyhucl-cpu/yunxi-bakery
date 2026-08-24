"""
用户 Query 改写。

把用户口语/指代不清的查询改写为独立完整的搜索语句。
"""

from functools import lru_cache

from app.logger import setup_logger
from app.service.agents.llm import get_langchain_chat_model
from app.service.privacy_redaction import redact_external_text


logger = setup_logger()

# 查询改写 LLM 调用的 max_tokens 上限（改写结果通常较短，严格限制避免浪费）
QUERY_REWRITER_MAX_TOKENS = 128

REWRITE_PROMPT = """### 角色
你是一个专门服务于「芸熙烘焙」AI 客服系统的顾客问题理解与改写专家。你的任务是结合对话历史上下文，充分理解顾客当前简短或指代不清的输入，并将其扩充、改写为一个完整、独立且表意清晰的查询语句，以便下游系统（如意图识别、知识库检索）能准确执行。

### 工作流程
#### 步骤一：结合上下文信息理解用户问题
- 你必须结合多轮对话历史和顾客当前的输入，准确判断顾客真实的需求。例如：顾客先问"草莓炸弹蛋糕多少钱"，客服回答后，顾客接着问"那6寸的呢？"，此时结合上下文，你需要理解顾客的真实意图是询问"草莓炸弹蛋糕6寸的价格是多少"。
- 重点识别并补全顾客输入中的代词（如"这个"、"那个"）、省略的商品主体、尺寸、时间或服务类型。

#### 步骤二：对用户问题进行重新描述与改写
- 结合步骤一的分析，如果顾客当前输入存在指代不明或省略成分，你必须对其进行重写。
- 改写后的句子必须是一个主谓宾完整的独立句子，直接包含具体的商品名、尺寸、地点或意图。
- 如果顾客当前的问题本身已经非常完整独立，无需依赖上下文即可理解，则直接输出原问题。

### 示例
#### 示例 1
历史记录：
用户：草莓蛋糕怎么卖呀？
AI：您好，草莓蛋糕4寸128元哦。
当前用户输入：那配送吗？
输出：草莓蛋糕支持同城配送吗？

#### 示例 2
历史记录：无
当前用户输入：你们银河SOHO店具体在几层？
输出：你们银河SOHO店具体在几层？

#### 示例 3
历史记录：
用户：明天下午我要一个黑森林。
AI：好的，请问要几寸的呢？
当前用户输入：三个人吃，你推荐一下。
输出：三个人吃黑森林蛋糕，推荐多大尺寸的？

### 限制
- 保持顾客原本的情感和核心意图不变，仅补全缺失的信息。
- **绝对严格限制：** 你的输出必须且只能是改写后的完整问题句子本身，绝对不能包含任何前缀语（如"改写后为："、"输出："）、多余的解释、换行符或引号。

历史记录：
{history}
当前用户输入：{user_query}"""


@lru_cache(maxsize=1)
def _get_rewrite_prompt_template():
    """延迟构建查询改写提示模板，避免模块导入阶段加载重依赖。"""
    from langchain_core.prompts import ChatPromptTemplate

    return ChatPromptTemplate.from_template(REWRITE_PROMPT)


async def rewrite_query(user_query: str, history: str = "") -> str:
    """
    改写用户查询为完整独立的搜索语句。

    参数：
        user_query: 用户当前输入
        history: 最近的对话历史文本（可选）
    返回：
        改写后的完整查询句子，失败返回原始输入
    """
    if len(user_query) < 2:
        return user_query

    try:
        rewritten = await _invoke_rewrite_chain(
            history=history or "无",
            user_query=user_query,
        )
        rewritten = rewritten.strip()
        # 清理可能的引用标记
        for ch in ['"', "'", "“", "”", "‘", "’"]:
            rewritten = rewritten.strip(ch)
        if not rewritten or len(rewritten) < 2:
            return user_query
        if rewritten != user_query:
            logger.debug("Query 改写: '%s' -> '%s'", user_query, rewritten)
        return rewritten
    except Exception as exc:
        logger.warning("Query 改写跳过: %s", exc)
        return user_query


async def _invoke_rewrite_chain(*, history: str, user_query: str) -> str:
    """通过统一 LangChain Runnable 执行查询改写。"""
    model = get_langchain_chat_model(provider="mimo", temperature=0.1).bind(
        max_tokens=QUERY_REWRITER_MAX_TOKENS
    )
    from langchain_core.output_parsers import StrOutputParser

    chain = _get_rewrite_prompt_template() | model | StrOutputParser()
    return await chain.ainvoke(
        {
            "history": redact_external_text(history),
            "user_query": redact_external_text(user_query),
        }
    )
