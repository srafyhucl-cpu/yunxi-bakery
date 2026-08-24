"""企微员工助手自由问法探针样本。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class EmployeeAgentProbeCase:
    name: str
    query: str
    expected_intent: str
    expected_tools: tuple[str, ...] = ()
    expected_kind: str = ""
    expected_date_from: str = ""
    expected_date_to: str = ""
    expected_date_field: str = ""
    expected_statuses: tuple[str, ...] = ()
    expected_keyword: str | None = None
    expected_missing_logistics: bool | None = None
    expected_needs_refund: bool | None = None
    expected_fulfillment_risk: bool | None = None
    expected_delivery_time_start: str = ""
    expected_delivery_time_end: str = ""
    required_any_terms: tuple[str, ...] = ()
    required_all_terms: tuple[str, ...] = ()
    required_all_term_groups: tuple[tuple[str, ...], ...] = ()
    forbidden_terms: tuple[str, ...] = ()
    allow_empty_result: bool = False
    allow_handoff: bool = True


MISSING_LOGISTICS_EXCLUSION_FORBIDDEN_TERMS = (
    "已剔除",
    "不含已关闭",
    "不含退款",
    "剔除已关闭",
    "剔除退款",
)
FULFILLMENT_RISK_RELATIVE_DATE_FORBIDDEN_TERMS = (
    "明天",
    "后天",
    "周末",
    "下周",
)
FULFILLMENT_RISK_DETOUR_FORBIDDEN_TERMS = (
    "需在",
    "前完成",
    "前安排",
)


def default_probe_cases(today: date) -> tuple[EmployeeAgentProbeCase, ...]:
    today_text = today.isoformat()
    yesterday_text = date.fromordinal(today.toordinal() - 1).isoformat()
    tomorrow_text = date.fromordinal(today.toordinal() + 1).isoformat()
    after_tomorrow_text = date.fromordinal(today.toordinal() + 2).isoformat()
    weekend_start_text, weekend_end_text = _weekend_text_range(today)
    next_monday_text = _weekday_text(today, 0, is_next_week=True)
    friday_text = _weekday_text(today, 4, is_next_week=False)
    recent_three_days_text = date.fromordinal(today.toordinal() - 2).isoformat()
    week_start_text = date.fromordinal(today.toordinal() - today.weekday()).isoformat()
    previous_week_start_text = date.fromordinal(
        today.toordinal() - today.weekday() - 7
    ).isoformat()
    previous_week_end_text = date.fromordinal(
        today.toordinal() - today.weekday() - 1
    ).isoformat()
    month_start_text = today.replace(day=1).isoformat()
    month_day_text = date(today.year, 7, 5).isoformat()
    return (
        *_order_summary_probe_cases(
            today_text,
            month_start_text,
            previous_week_start_text,
            previous_week_end_text,
        ),
        *_order_list_probe_cases(
            today_text,
            tomorrow_text,
            after_tomorrow_text,
            weekend_start_text,
            weekend_end_text,
            next_monday_text,
        ),
        *_order_product_probe_cases(
            today_text,
            recent_three_days_text,
            week_start_text,
            month_day_text,
            friday_text,
        ),
        *_channel_tool_probe_cases(),
        *_ops_status_probe_cases(),
        *_ops_business_probe_cases(),
        *_casual_order_probe_cases(today_text),
        *_casual_support_probe_cases(),
        *_p2c_employee_eval_expansion_probe_cases(today_text, yesterday_text),
    )


def _order_summary_probe_cases(
    today_text: str,
    month_start_text: str,
    previous_week_start_text: str,
    previous_week_end_text: str,
) -> tuple[EmployeeAgentProbeCase, ...]:
    return (
        EmployeeAgentProbeCase(
            "today-order-summary",
            "今天一共多少订单",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            today_text,
            today_text,
            expected_keyword="",
            required_any_terms=("单",),
            forbidden_terms=("完整订单号",),
        ),
        EmployeeAgentProbeCase(
            "yesterday-completed-summary",
            "昨天已完成多少订单",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            date.fromordinal(
                date.fromisoformat(today_text).toordinal() - 1
            ).isoformat(),
            date.fromordinal(
                date.fromisoformat(today_text).toordinal() - 1
            ).isoformat(),
            expected_keyword="",
            required_any_terms=("单",),
            forbidden_terms=("商品关键词“已完成”", "完整订单号"),
        ),
        EmployeeAgentProbeCase(
            "today-revenue-summary",
            "今天营业额多少",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            today_text,
            today_text,
            expected_keyword="",
            required_any_terms=("元", "营业额", "销售额"),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "未找到",
                "暂无数据",
                "暂无销售额",
                "暂无营业额",
                "无销售额",
                "无营业额",
                "后台订单页",
                "后台订单页核对",
                "请确认查询条件",
            ),
        ),
        EmployeeAgentProbeCase(
            "today-refund-summary",
            "今天有退款订单吗",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            today_text,
            today_text,
            expected_keyword="",
            expected_needs_refund=True,
            required_any_terms=("退款", "售后", "退单", "单"),
            forbidden_terms=("退款规则", "话术", "完整订单号", "手机号"),
        ),
        EmployeeAgentProbeCase(
            "this-month-revenue-summary",
            "本月销售额怎么样",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            month_start_text,
            today_text,
            expected_keyword="",
            required_any_terms=("元", "销售额", "营业额"),
            forbidden_terms=("完整订单号", "手机号", "后台订单页核对"),
        ),
        EmployeeAgentProbeCase(
            "last-week-refund-summary",
            "上周退款多少",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            previous_week_start_text,
            previous_week_end_text,
            expected_keyword="",
            expected_needs_refund=True,
            required_any_terms=("退款", "售后", "退单", "元", "单"),
            forbidden_terms=("退款规则", "话术", "完整订单号", "手机号"),
        ),
    )


def _order_list_probe_cases(
    today_text: str,
    tomorrow_text: str,
    after_tomorrow_text: str,
    weekend_start_text: str,
    weekend_end_text: str,
    next_monday_text: str,
) -> tuple[EmployeeAgentProbeCase, ...]:
    return (
        EmployeeAgentProbeCase(
            "pending-shipment-customer-reply",
            "还有哪些没发货，怎么跟客户说",
            "multi_tool",
            ("order_dynamic_query", "knowledge_answer"),
            "list",
            expected_statuses=("WAIT_SELLER_SEND_GOODS",),
            expected_keyword="",
            required_all_terms=("客户", "回复"),
            required_any_terms=("待发货", "未发货", "发货", "可复制", "话术"),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
        ),
        EmployeeAgentProbeCase(
            "pending-shipment-list",
            "还有哪些没发货",
            "order_query",
            ("order_dynamic_query",),
            "list",
            expected_statuses=("WAIT_SELLER_SEND_GOODS",),
            expected_keyword="",
            required_all_terms=("尾号", "待发货", "物流"),
            required_any_terms=("待发货", "未发货", "发货"),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "未在系统匹配",
                "未找到匹配商品",
            )
            + MISSING_LOGISTICS_EXCLUSION_FORBIDDEN_TERMS,
        ),
        EmployeeAgentProbeCase(
            "missing-logistics-list",
            "还没物流的订单有哪些",
            "order_query",
            ("order_dynamic_query",),
            "list",
            expected_missing_logistics=True,
            expected_keyword="",
            required_all_terms=("尾号", "物流"),
            required_any_terms=("待发货", "待收货", "已关闭", "交易成功"),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "未在系统匹配",
                "未找到匹配商品",
            ),
        ),
        EmployeeAgentProbeCase(
            "fulfillment-risk-list",
            "哪些单快超时了",
            "order_query",
            ("order_dynamic_query",),
            "list",
            expected_statuses=("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS"),
            expected_keyword="",
            expected_fulfillment_risk=True,
            required_all_terms=("尾号", "约送", "物流"),
            required_any_terms=("超时", "约送", "待发货", "待收货", "发货"),
            forbidden_terms=("完整订单号", "手机号", "完整地址")
            + FULFILLMENT_RISK_RELATIVE_DATE_FORBIDDEN_TERMS
            + FULFILLMENT_RISK_DETOUR_FORBIDDEN_TERMS,
        ),
        EmployeeAgentProbeCase(
            "evening-pending-orders",
            "晚上还有哪些待处理订单",
            "order_query",
            ("order_dynamic_query",),
            "list",
            today_text,
            today_text,
            "delivery_time",
            expected_statuses=("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS"),
            expected_keyword="",
            expected_delivery_time_start="18:00",
            expected_delivery_time_end="23:59",
            required_any_terms=("待处理", "约送", "晚上", "待发货", "待收货"),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "完整地址",
                "换商品名",
                "时间范围再查",
                "确认日期是否正确",
            ),
        ),
        EmployeeAgentProbeCase(
            "tomorrow-pending-orders",
            "明天有哪些待处理订单",
            "order_query",
            ("order_dynamic_query",),
            "list",
            tomorrow_text,
            tomorrow_text,
            "delivery_time",
            expected_statuses=("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS"),
            expected_keyword="",
            required_any_terms=("待处理", "约送", "明天", "待发货", "待收货"),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
        ),
        EmployeeAgentProbeCase(
            "tomorrow-preorder-orders",
            "有没有明天的预定订单",
            "order_query",
            ("order_dynamic_query",),
            "list",
            tomorrow_text,
            tomorrow_text,
            "delivery_time",
            expected_statuses=("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS"),
            expected_keyword="",
            required_any_terms=("待处理", "约送", "明天", "待发货", "待收货"),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "完整地址",
                "商品关键词",
                "下单日期",
            ),
        ),
        EmployeeAgentProbeCase(
            "after-tomorrow-pending-orders",
            "后天有哪些待处理订单",
            "order_query",
            ("order_dynamic_query",),
            "list",
            after_tomorrow_text,
            after_tomorrow_text,
            "delivery_time",
            expected_statuses=("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS"),
            expected_keyword="",
            required_any_terms=("待处理", "约送", "后天", "待发货", "待收货"),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "完整地址",
                "换商品名",
                "时间范围再查",
                "确认日期是否正确",
            ),
        ),
        EmployeeAgentProbeCase(
            "weekend-pending-orders",
            "周末有哪些待处理订单",
            "order_query",
            ("order_dynamic_query",),
            "list",
            weekend_start_text,
            weekend_end_text,
            "delivery_time",
            expected_statuses=("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS"),
            expected_keyword="",
            required_any_terms=("待处理", "约送", "周末", "待发货", "待收货"),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
        ),
        EmployeeAgentProbeCase(
            "next-monday-pending-orders",
            "下周一有哪些待处理订单",
            "order_query",
            ("order_dynamic_query",),
            "list",
            next_monday_text,
            next_monday_text,
            "delivery_time",
            expected_statuses=("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS"),
            expected_keyword="",
            required_any_terms=("待处理", "约送", "下周一", "待发货", "待收货"),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "完整地址",
                "换商品名",
                "时间范围再查",
                "确认日期是否正确",
            ),
        ),
    )


def _order_product_probe_cases(
    today_text: str,
    recent_three_days_text: str,
    week_start_text: str,
    month_day_text: str,
    friday_text: str,
) -> tuple[EmployeeAgentProbeCase, ...]:
    return (
        EmployeeAgentProbeCase(
            "product-order-summary",
            "椰椰凤梨今天卖了几单",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            today_text,
            today_text,
            expected_keyword="椰椰凤梨",
            required_any_terms=("单",),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "未在系统匹配",
                "未找到匹配商品",
            ),
        ),
        EmployeeAgentProbeCase(
            "recent-days-product-order-summary",
            "最近3天椰椰凤梨卖了几单",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            recent_three_days_text,
            today_text,
            expected_keyword="椰椰凤梨",
            required_any_terms=("单",),
            forbidden_terms=("完整订单号", "手机号"),
        ),
        EmployeeAgentProbeCase(
            "month-day-product-order-summary",
            "7月5日椰椰凤梨卖了几单",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            month_day_text,
            month_day_text,
            expected_keyword="椰椰凤梨",
            required_any_terms=("单",),
            forbidden_terms=("完整订单号", "手机号"),
        ),
        EmployeeAgentProbeCase(
            "friday-product-order-summary",
            "周五椰椰凤梨卖了几单",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            friday_text,
            friday_text,
            expected_keyword="椰椰凤梨",
            required_any_terms=("单",),
            forbidden_terms=("完整订单号", "手机号"),
        ),
        EmployeeAgentProbeCase(
            "top-products",
            "今天哪个商品卖得多",
            "order_query",
            ("order_dynamic_query",),
            "top_products",
            today_text,
            today_text,
            expected_keyword="",
            required_any_terms=("销量",),
            forbidden_terms=("完整订单号", "手机号", "优先备货"),
        ),
        EmployeeAgentProbeCase(
            "this-week-top-products",
            "本周哪个商品卖得多",
            "order_query",
            ("order_dynamic_query",),
            "top_products",
            week_start_text,
            today_text,
            expected_keyword="",
            required_any_terms=("销量",),
            forbidden_terms=("完整订单号", "手机号", "优先备货"),
        ),
        EmployeeAgentProbeCase(
            "this-week-revenue-summary",
            "本周销售额怎么样",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            week_start_text,
            today_text,
            expected_keyword="",
            required_any_terms=("元", "销售额", "营业额"),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "未找到",
                "暂无数据",
                "暂无销售额",
                "暂无营业额",
                "无销售额",
                "无营业额",
                "后台订单页",
                "后台订单页核对",
                "请确认查询条件",
            ),
        ),
        EmployeeAgentProbeCase(
            "this-week-refund-summary",
            "本周退款多少",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            week_start_text,
            today_text,
            expected_keyword="",
            expected_needs_refund=True,
            required_any_terms=("退款", "售后", "退单", "元", "单"),
            forbidden_terms=("退款规则", "话术", "完整订单号", "手机号"),
        ),
        EmployeeAgentProbeCase(
            "order-product-inventory",
            "今天订单里有伯牙绝弦吗，库存还够吗",
            "multi_tool",
            ("order_dynamic_query", "product_lookup"),
            "list",
            today_text,
            today_text,
            expected_keyword="伯牙绝弦",
            required_all_terms=("库存",),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "未匹配到商品",
                "未在系统匹配",
                "未找到匹配商品",
                "低库存",
            ),
        ),
    )


def _channel_tool_probe_cases() -> tuple[EmployeeAgentProbeCase, ...]:
    return (
        EmployeeAgentProbeCase(
            "casual-inventory",
            "伯牙绝弦还有吗",
            "product_query",
            ("product_lookup",),
            required_all_terms=("库存",),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "未匹配到商品",
                "未在系统匹配",
                "未找到匹配商品",
                "低库存",
            ),
        ),
        EmployeeAgentProbeCase(
            "no-stock-product",
            "招牌牛奶吐司还有吗",
            "product_query",
            ("product_lookup",),
            required_all_term_groups=(
                ("库存", "0", "暂无可售库存", "不要承诺有货", "替代款"),
                ("未找到匹配商品", "未命中结果", "缺货结论"),
            ),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "完整地址",
                "比如",
                "例如",
                "北海道吐司",
                "北海道牛奶吐司",
                "经典白吐司",
                "原味手撕包",
            ),
        ),
        EmployeeAgentProbeCase(
            "missing-product",
            "不存在的月球蛋糕还有吗",
            "product_query",
            ("product_lookup",),
            required_all_terms=("未找到匹配商品", "未命中结果", "缺货结论"),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
        ),
        EmployeeAgentProbeCase(
            "product-stock-recommend-replacement",
            "伯牙绝弦库存不够怎么推荐替代",
            "multi_tool",
            ("product_lookup", "knowledge_answer"),
            required_all_terms=("库存",),
            required_any_terms=("推荐", "替代", "客户", "回复"),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "完整地址",
                "未找到匹配知识",
                "未匹配到商品",
                "未在系统匹配",
                "未找到匹配商品",
                "低库存",
            ),
        ),
        EmployeeAgentProbeCase(
            "product-stock-customer-reply",
            "伯牙绝弦没货怎么跟客户说",
            "multi_tool",
            ("product_lookup", "knowledge_answer"),
            required_all_terms=("库存",),
            required_any_terms=("客户", "回复", "话术", "替代"),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "完整地址",
                "未找到匹配知识",
                "未匹配到商品",
                "未在系统匹配",
                "未找到匹配商品",
                "低库存",
            ),
        ),
        EmployeeAgentProbeCase(
            "delivery-knowledge",
            "明天能配送吗",
            "knowledge_answer",
            ("knowledge_answer",),
            required_all_terms=("配送",),
            required_any_terms=("排期", "确认", "人工", "可配送时段"),
            forbidden_terms=("订单尾号", "订单状态", "订单页", "后台订单"),
        ),
    )


def _ops_status_probe_cases() -> tuple[EmployeeAgentProbeCase, ...]:
    return (
        EmployeeAgentProbeCase(
            "ops-status",
            "系统今天有没有异常",
            "ops_query",
            ("ops_summary",),
            required_any_terms=("系统", "观察台", "状态"),
            forbidden_terms=("完整订单号", "手机号"),
        ),
        EmployeeAgentProbeCase(
            "integration-status",
            "同步失败有哪些",
            "ops_query",
            ("integration_status",),
            required_any_terms=("同步失败", "webhook", "Webhook", "失败"),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
        ),
        EmployeeAgentProbeCase(
            "handoff-pending",
            "现在有哪些待人工",
            "ops_query",
            ("handoff_pending",),
            required_any_terms=("待人工", "转人工"),
            forbidden_terms=("买家", "ID:", "user", "UMP", "type=card", "%E5%"),
        ),
    )


def _ops_business_probe_cases() -> tuple[EmployeeAgentProbeCase, ...]:
    return (
        EmployeeAgentProbeCase(
            "customer-lookup",
            "查一下张三地址线索",
            "ops_query",
            ("customer_lookup",),
            required_any_terms=("客户", "地址", "线索"),
            forbidden_terms=(
                "完整地址",
                "手机号",
                "买家ID",
                "订单尾号",
                "尾号",
                "后台订单",
                "未找到匹配客户地址",
            ),
        ),
        EmployeeAgentProbeCase(
            "group-campaign-summary",
            "汇总 campaignId:abc123",
            "ops_query",
            ("group_campaign_summary",),
            required_any_terms=(
                "群活动",
                "客户群",
                "campaignId",
                "campaign",
                "活动批次",
            ),
            forbidden_terms=(
                "手机号",
                "完整地址",
                "库存",
                "小程序商品",
                "退款",
                "后台订单",
                "请稍后重试",
                "活动批次不存在",
            ),
        ),
        EmployeeAgentProbeCase(
            "offline-review-summary",
            "昨晚离线复盘结果",
            "ops_query",
            ("offline_review_summary",),
            required_any_terms=("离线复盘", "复盘"),
            forbidden_terms=(
                "手机号",
                "完整地址",
                "买家ID",
                "outside_night_window",
                "skippedReason",
            ),
        ),
    )


def _casual_order_probe_cases(today_text: str) -> tuple[EmployeeAgentProbeCase, ...]:
    return (
        EmployeeAgentProbeCase(
            "today-action-items",
            "今天有什么要盯的",
            "order_query",
            ("order_dynamic_query",),
            "action_items",
            today_text,
            today_text,
            expected_keyword="",
            required_any_terms=("待处理", "履约", "退款", "物流", "单"),
            required_all_terms=("优先级", "压力"),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
        ),
        EmployeeAgentProbeCase(
            "casual-order-attention",
            "今天订单有没有需要注意的",
            "order_query",
            ("order_dynamic_query",),
            "action_items",
            today_text,
            today_text,
            expected_keyword="",
            required_any_terms=("待处理", "履约", "退款", "物流", "单"),
            required_all_terms=("优先级", "压力"),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
        ),
        EmployeeAgentProbeCase(
            "refund-order-customer-reply",
            "今天有退款订单，怎么回复客户",
            "multi_tool",
            ("order_dynamic_query", "knowledge_answer"),
            "summary",
            today_text,
            today_text,
            expected_keyword="",
            expected_needs_refund=True,
            required_all_terms=("客户", "回复"),
            required_any_terms=("退款", "售后", "可复制", "话术", "单"),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
        ),
        EmployeeAgentProbeCase(
            "casual-today-orders",
            "今天单量咋样",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            today_text,
            today_text,
            expected_keyword="",
            required_any_terms=("单",),
            forbidden_terms=("完整订单号", "手机号"),
        ),
        EmployeeAgentProbeCase(
            "casual-pending-shipment",
            "发货还有没处理的吗",
            "order_query",
            ("order_dynamic_query",),
            "list",
            expected_statuses=("WAIT_SELLER_SEND_GOODS",),
            expected_keyword="",
            required_all_terms=("尾号", "待发货", "物流"),
            required_any_terms=("待发货", "未发货", "发货"),
            forbidden_terms=("完整订单号", "手机号"),
        ),
        EmployeeAgentProbeCase(
            "casual-fulfillment-pressure",
            "今天发货压力大不大",
            "order_query",
            ("order_dynamic_query",),
            "list",
            today_text,
            today_text,
            expected_statuses=("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS"),
            expected_keyword="",
            expected_fulfillment_risk=True,
            required_all_terms=("发货压力", "尾号", "约送", "物流"),
            required_any_terms=("偏高", "中等", "低", "约送", "待发货", "待收货"),
            forbidden_terms=("完整订单号", "手机号", "完整地址", "压力不大")
            + FULFILLMENT_RISK_RELATIVE_DATE_FORBIDDEN_TERMS
            + FULFILLMENT_RISK_DETOUR_FORBIDDEN_TERMS,
        ),
        EmployeeAgentProbeCase(
            "casual-missing-logistics",
            "哪些单子还没出物流",
            "order_query",
            ("order_dynamic_query",),
            "list",
            expected_missing_logistics=True,
            expected_keyword="",
            required_all_terms=("尾号", "物流"),
            required_any_terms=("待发货", "待收货", "已关闭", "交易成功"),
            forbidden_terms=("完整订单号", "手机号")
            + MISSING_LOGISTICS_EXCLUSION_FORBIDDEN_TERMS,
        ),
        EmployeeAgentProbeCase(
            "casual-top-product",
            "今天卖爆的是哪个",
            "order_query",
            ("order_dynamic_query",),
            "top_products",
            today_text,
            today_text,
            expected_keyword="",
            required_any_terms=("销量", "卖", "爆款"),
            forbidden_terms=("完整订单号", "手机号", "优先备货"),
        ),
    )


def _casual_support_probe_cases() -> tuple[EmployeeAgentProbeCase, ...]:
    return (
        EmployeeAgentProbeCase(
            "casual-product-stock",
            "帮我看看伯牙绝弦库存",
            "product_query",
            ("product_lookup",),
            required_all_terms=("库存",),
            forbidden_terms=(
                "完整订单号",
                "手机号",
                "未匹配到商品",
                "未在系统匹配",
                "未找到匹配商品",
                "低库存",
            ),
        ),
        EmployeeAgentProbeCase(
            "casual-ops-status",
            "后台现在稳不稳",
            "ops_query",
            ("ops_summary",),
            required_any_terms=("系统", "观察台", "状态"),
            forbidden_terms=("完整订单号", "手机号"),
        ),
        EmployeeAgentProbeCase(
            "casual-handoff-pending",
            "有没有需要人接的",
            "ops_query",
            ("handoff_pending",),
            required_any_terms=("待人工", "转人工"),
            forbidden_terms=("买家", "ID:", "user", "UMP", "type=card", "%E5%"),
        ),
    )


def _p2c_employee_eval_expansion_probe_cases(
    today_text: str,
    yesterday_text: str,
) -> tuple[EmployeeAgentProbeCase, ...]:
    return (
        EmployeeAgentProbeCase(
            "p2c-yesterday-success-summary",
            "昨天交易成功多少订单",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            yesterday_text,
            yesterday_text,
            expected_statuses=("TRADE_SUCCESS",),
            expected_keyword="",
            required_any_terms=("交易成功", "已完成", "单"),
            forbidden_terms=("完整订单号", "手机号"),
        ),
        EmployeeAgentProbeCase(
            "p2c-today-closed-summary",
            "今天已关闭订单有几单",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            today_text,
            today_text,
            expected_statuses=("TRADE_CLOSED",),
            expected_keyword="",
            required_any_terms=("已关闭", "关闭", "单"),
            forbidden_terms=("完整订单号", "手机号"),
        ),
        EmployeeAgentProbeCase(
            "p2c-today-wait-buyer-confirm-list",
            "今天待收货订单有哪些",
            "order_query",
            ("order_dynamic_query",),
            "list",
            today_text,
            today_text,
            expected_statuses=("WAIT_BUYER_CONFIRM_GOODS",),
            expected_keyword="",
            required_all_terms=("尾号", "待收货"),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
            allow_empty_result=True,
        ),
        EmployeeAgentProbeCase(
            "p2c-today-wait-seller-send-list",
            "今天待发货订单有哪些",
            "order_query",
            ("order_dynamic_query",),
            "list",
            today_text,
            today_text,
            expected_statuses=("WAIT_SELLER_SEND_GOODS",),
            expected_keyword="",
            required_all_terms=("尾号", "待发货"),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
            allow_empty_result=True,
        ),
        EmployeeAgentProbeCase(
            "p2c-morning-pending-orders",
            "上午还有哪些待处理订单",
            "order_query",
            ("order_dynamic_query",),
            "list",
            today_text,
            today_text,
            "delivery_time",
            expected_statuses=("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS"),
            expected_keyword="",
            expected_delivery_time_start="06:00",
            expected_delivery_time_end="11:59",
            required_any_terms=("上午", "约送", "待处理", "待发货", "待收货"),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
        ),
        EmployeeAgentProbeCase(
            "p2c-afternoon-pending-orders",
            "下午还有哪些待处理订单",
            "order_query",
            ("order_dynamic_query",),
            "list",
            today_text,
            today_text,
            "delivery_time",
            expected_statuses=("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_CONFIRM_GOODS"),
            expected_keyword="",
            expected_delivery_time_start="12:00",
            expected_delivery_time_end="17:59",
            required_any_terms=("下午", "约送", "待处理", "待发货", "待收货"),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
        ),
        EmployeeAgentProbeCase(
            "p2c-strawberry-product-summary",
            "今天草莓蛋糕卖了几单",
            "order_query",
            ("order_dynamic_query",),
            "summary",
            today_text,
            today_text,
            expected_keyword="草莓蛋糕",
            required_any_terms=("草莓蛋糕", "单"),
            forbidden_terms=("完整订单号", "手机号"),
        ),
        EmployeeAgentProbeCase(
            "p2c-exact-order-detail",
            "E202600000000 这单详情",
            "order_query",
            ("order_dynamic_query",),
            "detail",
            required_any_terms=("订单", "详情", "尾号"),
            forbidden_terms=("完整地址", "手机号"),
        ),
        EmployeeAgentProbeCase(
            "p2c-exact-order-customer-history",
            "E202600000000 这个客户还买过什么",
            "order_query",
            ("order_dynamic_query",),
            "list",
            required_any_terms=("该客户", "历史订单", "买过"),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
        ),
        EmployeeAgentProbeCase(
            "p2c-refund-policy-knowledge",
            "退款规则是什么",
            "knowledge_answer",
            ("knowledge_answer",),
            required_any_terms=("退款", "售后", "规则"),
            forbidden_terms=("完整订单号", "手机号", "订单尾号"),
        ),
        EmployeeAgentProbeCase(
            "p2c-customer-lookup-li-si",
            "帮我查一下李四客户线索",
            "ops_query",
            ("customer_lookup",),
            required_any_terms=("客户", "线索"),
            forbidden_terms=("完整地址", "手机号", "完整订单号"),
        ),
        EmployeeAgentProbeCase(
            "p2c-customer-address-clue",
            "查一下王女士地址线索",
            "ops_query",
            ("customer_lookup",),
            required_any_terms=("客户", "地址", "线索"),
            forbidden_terms=("完整地址", "手机号", "完整订单号"),
        ),
        EmployeeAgentProbeCase(
            "p2c-unsupported-poem",
            "帮我写一首诗",
            "unsupported",
            (),
            forbidden_terms=("完整订单号", "手机号", "完整地址"),
        ),
    )


def _weekend_text_range(today: date) -> tuple[str, str]:
    week_start = date.fromordinal(today.toordinal() - today.weekday())
    weekend_start = date.fromordinal(week_start.toordinal() + 5)
    weekend_end = date.fromordinal(week_start.toordinal() + 6)
    if today > weekend_end:
        weekend_start = date.fromordinal(weekend_start.toordinal() + 7)
        weekend_end = date.fromordinal(weekend_end.toordinal() + 7)
    return weekend_start.isoformat(), weekend_end.isoformat()


def _weekday_text(today: date, target_weekday: int, *, is_next_week: bool) -> str:
    week_start = date.fromordinal(today.toordinal() - today.weekday())
    offset_days = target_weekday + (7 if is_next_week else 0)
    return date.fromordinal(week_start.toordinal() + offset_days).isoformat()
