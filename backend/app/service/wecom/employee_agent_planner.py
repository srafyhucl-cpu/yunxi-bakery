"""企微员工助手计划生成。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date

from app.logger import setup_logger
from app.models.employee_agent import AgentIntent, AgentPlan
from app.service.agents.employee.structured_planner import (
    request_employee_plan_with_langchain,
)
from app.service.wecom.employee_agent_capabilities import (
    AgentCapabilityCard,
    EmployeeAgentCapabilityRegistry,
)
from app.service.wecom.employee_agent_order_plan import build_rule_plan

logger = setup_logger()


class EmployeeAgentPlanner:
    """把员工自然语言转成结构化 AgentPlan。"""

    def __init__(
        self,
        *,
        capability_registry: EmployeeAgentCapabilityRegistry | None = None,
        today_provider: Callable[[], date] | None = None,
        enable_llm: bool = True,
    ) -> None:
        self._capability_registry = (
            capability_registry or EmployeeAgentCapabilityRegistry()
        )
        self._today_provider = today_provider or date.today
        self._enable_llm = enable_llm

    async def plan(self, query: str) -> AgentPlan:
        """优先规则规划，必要时降级到 LLM 计划。"""
        capabilities = self._capability_registry.search(query)
        rule_plan = build_rule_plan(query, capabilities, self._today_provider())
        if rule_plan.intent != AgentIntent.UNSUPPORTED:
            return rule_plan
        if not self._enable_llm:
            return rule_plan
        planning_capabilities = capabilities or self._capability_registry.all_cards()
        llm_plan = await self._plan_with_llm(query, planning_capabilities)
        return llm_plan or rule_plan

    async def _plan_with_llm(
        self,
        query: str,
        capabilities: list[AgentCapabilityCard],
    ) -> AgentPlan | None:
        try:
            return await request_employee_plan_with_langchain(
                query,
                capabilities,
            )
        except Exception as exc:
            logger.warning("企微员工助手 LangChain 规划失败，使用规则兜底: %s", exc)
        return None
