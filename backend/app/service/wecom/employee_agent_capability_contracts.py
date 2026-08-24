"""企微员工助手能力合约清单。"""

from __future__ import annotations

from dataclasses import dataclass

from app.service.wecom.employee_agent_capabilities import CAPABILITY_CARDS


@dataclass(frozen=True)
class EmployeeAgentCapabilityContract:
    """员工助手能力的参数、兜底和探针约束。"""

    name: str
    parameter_rules: tuple[str, ...]
    missing_parameter_reply: str
    empty_result_reply: str
    error_reply: str
    probe_names: tuple[str, ...]


CAPABILITY_CONTRACTS: tuple[EmployeeAgentCapabilityContract, ...] = (
    EmployeeAgentCapabilityContract(
        "order_dynamic_query",
        ("识别日期范围", "识别订单状态", "识别商品关键词", "只允许白名单查询字段"),
        "缺少时间或对象时追问员工补充日期、订单尾号、商品名或客户线索。",
        "说明查询口径和空结果范围，不建议员工绕开口径重新猜。",
        "提示订单查询暂不可用，引导去后台订单页按同一口径核对。",
        ("today-order-summary", "pending-shipment-list", "fulfillment-risk-list"),
    ),
    EmployeeAgentCapabilityContract(
        "product_lookup",
        ("识别商品名、品类、库存和价格问法", "不能把未命中当成缺货"),
        "缺少商品名时追问具体商品、品类或关键词。",
        "说明未找到匹配商品，不输出缺货结论。",
        "提示商品查询暂不可用，引导到后台商品页核对。",
        ("casual-inventory", "no-stock-product", "missing-product"),
    ),
    EmployeeAgentCapabilityContract(
        "knowledge_answer",
        ("识别配送、售后、退款、自提和对客话术问法", "只检索员工可见知识"),
        "缺少业务场景时追问员工要查配送、售后、商品还是对客回复。",
        "说明知识库未命中，并提示到后台知识库补充。",
        "提示知识库查询暂不可用，要求员工先按门店最新规则核对。",
        ("delivery-knowledge", "refund-order-customer-reply"),
    ),
    EmployeeAgentCapabilityContract(
        "ops_summary",
        ("识别系统状态、观察台和经营异常问法",),
        "缺少时间范围时默认查看当前观察台摘要。",
        "说明当前没有需要关注的观察台摘要。",
        "提示观察台摘要暂不可用，引导打开后台数据观察台。",
        ("ops-status", "casual-ops-status"),
    ),
    EmployeeAgentCapabilityContract(
        "integration_status",
        ("识别同步失败、Webhook、回调和第三方集成问法",),
        "缺少范围时默认查询最近失败或处理中记录。",
        "说明最近没有同步或回调失败记录。",
        "提示集成排障查询暂不可用，引导查看后台失败排查页。",
        ("integration-status",),
    ),
    EmployeeAgentCapabilityContract(
        "handoff_pending",
        ("识别待人工、转人工、待接单和人工处理问法",),
        "缺少范围时默认查询当前待处理人工会话。",
        "说明当前没有待人工处理会话。",
        "提示待人工列表暂不可用，引导打开后台转人工页面。",
        ("handoff-pending", "casual-handoff-pending"),
    ),
    EmployeeAgentCapabilityContract(
        "customer_lookup",
        ("识别客户姓名、手机号后四位或地址线索", "只返回脱敏预览"),
        "缺少客户线索时追问姓名、手机号后四位或订单尾号。",
        "说明未找到客户地址线索，要求人工继续核对。",
        "提示客户线索查询暂不可用，引导到后台客户/地址页核对。",
        ("customer-lookup",),
    ),
    EmployeeAgentCapabilityContract(
        "group_campaign_summary",
        ("识别 campaignId、客户群、团购和预订批次",),
        "缺少 campaignId 时追问活动批次 ID 或群登记链接。",
        "说明未找到该客户群活动批次。",
        "提示客户群汇总暂不可用，引导打开后台客户群运营页。",
        ("group-campaign-summary",),
    ),
    EmployeeAgentCapabilityContract(
        "offline_review_summary",
        ("识别离线复盘、夜间复盘、知识缺口和跳过原因",),
        "缺少时间时默认查询最近一轮离线复盘。",
        "说明最近没有可用离线复盘结果。",
        "提示离线复盘摘要暂不可用，引导查看后台或日志。",
        ("offline-review-summary",),
    ),
)


def capability_card_names() -> set[str]:
    """返回能力卡中的工具名。"""
    return {card.name for card in CAPABILITY_CARDS}


def capability_contracts_by_name() -> dict[str, EmployeeAgentCapabilityContract]:
    """返回按工具名索引的合约。"""
    return {contract.name: contract for contract in CAPABILITY_CONTRACTS}
