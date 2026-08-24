"""企微员工助手订单问法关键词。"""

from __future__ import annotations

ORDER_REVENUE_KEYWORDS = (
    "营业额",
    "销售额",
    "收入",
    "流水",
    "成交额",
    "卖了多少钱",
)
ORDER_REFUND_KEYWORDS = (
    "退款订单",
    "退款单",
    "退单",
    "退款",
    "售后订单",
    "售后单",
)
ORDER_FULFILLMENT_RISK_KEYWORDS = (
    "超时",
    "快超时",
    "要超时",
    "来不及",
    "赶不及",
    "发货压力",
    "履约压力",
    "优先处理",
)
ORDER_ACTION_ITEMS_KEYWORDS = (
    "要盯",
    "盯一下",
    "要处理",
    "需要处理",
    "需要注意",
    "注意的",
    "有啥事",
    "有什么事",
    "有什么要",
    "待办",
    "处理一下",
)
ORDER_POLICY_KEYWORDS = (
    "规则",
    "怎么说",
    "怎么跟客户说",
    "怎么回复客户",
    "回复客户",
    "话术",
    "政策",
    "说明",
)
ORDER_PREORDER_DELIVERY_KEYWORDS = (
    "预定",
    "预订",
    "要送",
    "待送",
)
ORDER_CUSTOMER_HISTORY_KEYWORDS = (
    "这个客户",
    "该客户",
    "客户历史单",
    "客户历史订单",
    "历史单",
    "历史订单",
    "还买过",
    "买过什么",
    "还下过",
)
ORDER_QUERY_KEYWORDS = (
    "订单",
    "单子",
    "单量",
    "单",
    "下单",
    "发货",
    "物流",
    "几单",
    "待处理",
    "卖得多",
    "卖爆",
    "销量",
    *ORDER_PREORDER_DELIVERY_KEYWORDS,
    *ORDER_REFUND_KEYWORDS,
    *ORDER_FULFILLMENT_RISK_KEYWORDS,
    *ORDER_ACTION_ITEMS_KEYWORDS,
    *ORDER_REVENUE_KEYWORDS,
)
