"""客户机器人 LangGraph 常量。"""

CUSTOMER_TOOL_ROUND_LIMIT = 3
LLM_FAILURE_REASON_TOOL_ROUND_LIMIT = "tool_round_limit"

TRANSFER_TOOL_NAME = "transfer_to_human"
TRANSFER_TOOL_DEFAULT_REASON = "用户通过工具请求转人工"
TRANSFER_TOOL_SUCCESS_MESSAGE = "已为您转接人工客服，请稍候"
TRANSFER_TOOL_ERROR_MESSAGE = "转接失败，请稍后重试"
