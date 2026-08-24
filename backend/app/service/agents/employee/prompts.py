"""员工助手 LangChain planner prompt。"""

from app.service.wecom.employee_agent_capabilities import AgentCapabilityCard


def build_employee_planner_messages(
    query: str,
    capabilities: list[AgentCapabilityCard],
) -> list[tuple[str, str]]:
    """构造员工助手结构化规划消息。"""
    capability_text = "\n".join(
        f"- {card.name}: {card.description}；示例：{' / '.join(card.examples)}"
        for card in capabilities
    )
    return [
        (
            "system",
            "你是芸熙烘焙内部员工助手的规划器。"
            "只生成结构化执行计划，不回答员工问题，不生成 SQL。",
        ),
        (
            "user",
            "只能使用这些 intent: order_query, product_query, "
            "knowledge_answer, ops_query, multi_tool, unsupported。\n"
            f"可用能力：\n{capability_text or '无'}\n"
            f"员工问题：{query}\n"
            "输出字段必须匹配结构化 schema：intent, tools, queryPlan, answerStyle。",
        ),
    ]
