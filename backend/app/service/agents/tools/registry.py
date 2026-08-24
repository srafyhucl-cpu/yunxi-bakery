"""LangChain 工具注册表。"""

from typing import Any, Literal

from app.service.agents.tools.customer import CustomerToolContext
from app.service.agents.tools.employee import EmployeeToolContext

BotToolScope = Literal["customer", "employee"]


def build_tools(
    scope: BotToolScope,
    *,
    customer_context: CustomerToolContext | None = None,
    employee_context: EmployeeToolContext | None = None,
) -> list[Any]:
    """按机器人范围构造 LangChain 工具。"""
    if scope == "customer":
        from app.service.agents.tools.customer import build_customer_tools

        return build_customer_tools(customer_context or CustomerToolContext())
    if scope == "employee":
        from app.service.agents.tools.employee import build_employee_tools

        return build_employee_tools(employee_context or EmployeeToolContext())

    msg = f"未知工具范围: {scope}"
    raise ValueError(msg)
