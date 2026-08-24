"""企微智能机器人运营类只读工具服务。"""

from typing import Any

from app.logger import setup_logger
from app.service.wecom.intelligent_bot_plugin import extract_text
from app.service.wecom.intelligent_bot_tool_response import (
    extract_limit,
    failed,
    missing_query,
    ok_response,
    unavailable,
)
from app.service.wecom.intelligent_bot_ops_format import (
    address_line,
    compact_address,
    compact_group_followup,
    compact_transfer,
    customer_lookup_empty_line,
    customer_lookup_empty_next_action,
    customer_lookup_query_preview,
    group_campaign_missing_line,
    group_campaign_missing_next_action,
    group_summary_line,
    transfer_line,
)

logger = setup_logger()
CUSTOMER_LOOKUP_NOISE_TERMS = (
    "帮我查一下",
    "帮我看看",
    "查一下",
    "查询",
    "客户",
    "收货地址",
    "地址线索",
    "地址",
    "有没有",
    "有吗",
)
CUSTOMER_LOOKUP_STRIP_CHARS = " ：:，,。？?的"


class WeComBotOpsToolService:
    """把客户、群运营、转人工和观察台包装成企微只读工具。"""

    def __init__(
        self,
        *,
        customer_address_service: Any = None,
        customer_group_service: Any = None,
        transfer_mgr: Any = None,
    ) -> None:
        self._customer_address_service = customer_address_service
        self._customer_group_service = customer_group_service
        self._transfer_mgr = transfer_mgr

    async def lookup_customer(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_query = extract_text(payload)
        query = _normalize_customer_lookup_query(raw_query)
        if self._customer_address_service is None:
            return unavailable("customer_lookup", "客户查询")
        if not query:
            return missing_query("customer_lookup", "请提供客户姓名或地址关键词。")
        try:
            result = await self._customer_address_service.list_admin_addresses(
                page=1,
                keyword=query,
            )
        except Exception as exc:
            logger.error("企微客户查询工具失败 query=%s err=%s", query, exc)
            return failed("customer_lookup", "客户查询失败，请稍后重试或到后台查看。")
        addresses = [compact_address(item) for item in result.get("items", [])]
        addresses_text = "\n".join(address_line(item) for item in addresses)
        return ok_response(
            "customer_lookup",
            customer_lookup_query_preview(query),
            f"找到 {result.get('total', len(addresses))} 条地址/客户线索。",
            addresses=addresses,
            addressesText=addresses_text or customer_lookup_empty_line(query),
            nextAction=_customer_lookup_next_action(addresses),
        )

    async def summarize_group_campaign(self, payload: dict[str, Any]) -> dict[str, Any]:
        campaign_id = _extract_named_text(payload, "campaignId")
        if self._customer_group_service is None:
            return unavailable("group_campaign_summary", "客户群批次汇总")
        if not campaign_id:
            return missing_query("group_campaign_summary", "请提供 campaignId。")
        try:
            summary = await self._customer_group_service.get_campaign_summary(
                campaign_id
            )
        except ValueError:
            missing_summary = group_campaign_missing_line(campaign_id)
            return ok_response(
                "group_campaign_summary",
                campaign_id,
                missing_summary,
                summaryText=missing_summary,
                campaign={},
                productTotals=[],
                pendingFollowups=[],
                nextAction=group_campaign_missing_next_action(),
            )
        except Exception as exc:
            logger.error("企微客户群汇总工具失败 campaign=%s err=%s", campaign_id, exc)
            return failed("group_campaign_summary", "客户群汇总失败，请稍后重试。")
        return ok_response(
            "group_campaign_summary",
            campaign_id,
            group_summary_line(summary),
            summaryText=str(summary.get("summaryText", "")),
            campaign=summary.get("campaign", {}),
            productTotals=summary.get("productTotals", []),
            pendingFollowups=[
                compact_group_followup(item)
                for item in summary.get("pendingFollowups", [])
            ],
            nextAction="可复制 summaryText 发群；待确认用户建议单独跟进。",
        )

    async def list_pending_handoffs(self, payload: dict[str, Any]) -> dict[str, Any]:
        limit = extract_limit(payload)
        if self._transfer_mgr is None:
            return unavailable("handoff_pending", "待人工列表")
        try:
            transfers = await self._transfer_mgr.get_pending()
        except Exception as exc:
            logger.error("企微待人工工具失败 err=%s", exc)
            return failed("handoff_pending", "待人工列表读取失败，请稍后重试。")
        items = [compact_transfer(item) for item in transfers[:limit]]
        transfers_text = "\n".join(transfer_line(item) for item in items)
        return ok_response(
            "handoff_pending",
            "pending",
            f"当前待人工 {len(transfers)} 个，返回 {len(items)} 个。",
            transfers=items,
            transfersText=transfers_text or "当前没有待人工工单。",
            nextAction="需要接单或关闭时，请进入后台转人工队列处理。",
        )


def _extract_named_text(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    return value.strip() if isinstance(value, str) else extract_text(payload)


def _normalize_customer_lookup_query(query: str) -> str:
    clean_query = query.strip()
    for noise_term in CUSTOMER_LOOKUP_NOISE_TERMS:
        clean_query = clean_query.replace(noise_term, "")
    return clean_query.strip(CUSTOMER_LOOKUP_STRIP_CHARS)


def _customer_lookup_next_action(addresses: list[dict[str, Any]]) -> str:
    if addresses:
        return "这是地址簿线索，不等于完整 CRM 主档；重要操作请人工核对。"
    return customer_lookup_empty_next_action()
