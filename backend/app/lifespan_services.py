"""lifespan 阶段 Service 层初始化逻辑（从 main.py 拆出）。

第一阶段平台化重组后，这里优先装配 Platform 的 canonical 领域服务名，
同时保留旧 miniapp_* key 作为兼容别名，避免现有路由和测试立即失效。
"""

from typing import Any

from app.config import settings
from app.models.knowledge import KnowledgeAudience
from app.service.chat import ChatService
from app.service.knowledge_retriever import KnowledgeRetriever
from app.service.youzan.client import YouzanClient
from app.service.youzan.event_handler import YouzanEventHandler
from app.service.youzan.product_reconciler import ProductReconcileService
from app.service.agents.trace_sink import build_local_agent_trace_sink
from app.repository.privacy_repo import PrivacyRepo

LEGACY_SERVICE_ALIASES = {
    "miniapp_auth_service": "storefront_auth_service",
    "miniapp_catalog_service": "catalog_service",
    "miniapp_order_service": "order_service",
    "miniapp_address_service": "customer_address_service",
    "miniapp_chat_service": "storefront_conversation_service",
    "shop_page_config_service": "shop_page_configuration_service",
}


def init_services(repos: dict[str, Any], vs: Any, bm25: Any = None) -> dict[str, Any]:
    """初始化 Service 层，返回服务字典。"""
    trace_sink = build_local_agent_trace_sink(
        enabled=settings.AGENT_LOCAL_TRACE_ENABLED,
        path=settings.AGENT_LOCAL_TRACE_PATH,
    )
    knowledge_retriever = KnowledgeRetriever(
        repos["knowledge_repo"],
        vs,
        config_repo=repos["config_repo"],
        bm25=bm25,
        audience=KnowledgeAudience.CUSTOMER.value,
        youzan_product_repo=repos["youzan_product_repo"],
    )
    employee_knowledge_retriever = KnowledgeRetriever(
        repos["knowledge_repo"],
        vs,
        config_repo=repos["config_repo"],
        bm25=bm25,
        audience=KnowledgeAudience.EMPLOYEE.value,
        youzan_product_repo=repos["youzan_product_repo"],
    )

    from app.service.admin import AdminService
    from app.service.catalog import CatalogApplicationService
    from app.service.channels.storefront import StorefrontAuthService
    from app.service.conversation import StorefrontConversationService
    from app.service.customer import CustomerAddressService
    from app.service.customer import CustomerGroupOperationsService
    from app.service.customer_consent import CustomerConsentService
    from app.service.privacy_lifecycle import PrivacyLifecycleService
    from app.service.observability import ObservabilityService
    from app.service.ops import (
        ShopConfigurationService,
        ShopPageConfigurationService,
    )
    from app.service.order import OrderApplicationService
    from app.service.transfer_manager import TransferManager
    from app.service.wecom.employee_agent_service import EmployeeAgentService
    from app.service.wecom.intelligent_bot_ops_tools import WeComBotOpsToolService
    from app.service.wecom.intelligent_bot_order_lookup import WeComOrderLookupService
    from app.service.wecom.intelligent_bot_status_tools import WeComBotStatusToolService
    from app.service.wecom.intelligent_bot_tools import WeComBotBusinessToolService

    admin_service = AdminService(
        session_repo=repos["session_repo"],
        message_repo=repos["message_repo"],
        transfer_repo=repos["transfer_repo"],
        knowledge_repo=repos["knowledge_repo"],
        config_repo=repos["config_repo"],
        youzan_product_repo=repos["youzan_product_repo"],
        knowledge_product_repo=repos["knowledge_product_repo"],
        knowledge_admin_repo=repos["knowledge_admin_repo"],
        history_repo=repos["history_repo"],
    )
    observability_service = ObservabilityService(
        knowledge_repo=repos["knowledge_repo"],
        product_repo=repos["youzan_product_repo"],
        history_repo=repos["history_repo"],
        webhook_repo=repos["webhook_event_repo"],
    )
    knowledge_services = _init_knowledge_management_services(repos, vs)
    catalog_service = CatalogApplicationService(
        product_repo=repos["knowledge_product_repo"],
        knowledge_repo=repos["knowledge_repo"],
        config_repo=repos["config_repo"],
        youzan_product_repo=repos["youzan_product_repo"],
    )
    from app.service.stored_value import StoredValueService

    stored_value_service = StoredValueService()
    from app.service.points import PointsService

    points_service = PointsService()
    from app.service.coupon import CouponService

    coupon_service = CouponService()
    order_service = OrderApplicationService(
        order_repo=repos["order_repo"],
        event_repo=repos["order_event_repo"],
        session_repo=repos["session_repo"],
        product_repo=repos["youzan_product_repo"],
        inventory_repo=repos["youzan_inventory_repo"],
        config_repo=repos["config_repo"],
        stored_value_service=stored_value_service,
    )
    customer_address_service = CustomerAddressService(
        address_repo=repos["customer_address_repo"],
        audit_repo=repos["customer_address_audit_repo"],
    )
    customer_group_service = CustomerGroupOperationsService(
        repos["customer_group_repo"]
    )
    storefront_auth_service = StorefrontAuthService()
    customer_consent_service = CustomerConsentService(repos["customer_profile_repo"])
    privacy_lifecycle_service = PrivacyLifecycleService(
        repos.get("privacy_repo") or PrivacyRepo(None)
    )
    transfer_mgr = TransferManager(repos["transfer_repo"])
    shop_page_configuration_service = ShopPageConfigurationService(repos["config_repo"])
    shop_configuration_service = ShopConfigurationService(repos["config_repo"])

    youzan_client = YouzanClient(config_repo=repos["config_repo"])
    youzan_event_handler = YouzanEventHandler(
        db=None,
        knowledge_retriever=knowledge_retriever,
        youzan_client=youzan_client,
        audit_repo=repos["webhook_event_repo"],
    )
    reconcile_service = ProductReconcileService(
        youzan_client=youzan_client,
        product_repo=repos["youzan_product_repo"],
        history_repo=repos["history_repo"],
        knowledge_product_repo=repos["knowledge_product_repo"],
        embedding_searcher=vs,
    )

    chat_service = ChatService(
        session_repo=repos["session_repo"],
        message_repo=repos["message_repo"],
        transfer_repo=repos["transfer_repo"],
        knowledge_retriever=knowledge_retriever,
        youzan_client=youzan_client,
        youzan_webhook_events_repo=repos["webhook_event_repo"],
        youzan_event_handler=youzan_event_handler,
        analytics_repo=repos["analytics_repo"],
        customer_profile_repo=repos.get("customer_profile_repo"),
        conversation_summary_repo=repos.get("conversation_summary_repo"),
        trace_sink=trace_sink,
        order_repo=repos.get("youzan_order_repo"),
        config_repo=repos["config_repo"],
        product_repo=repos["youzan_product_repo"],
        knowledge_product_repo=repos["knowledge_product_repo"],
        history_repo=repos["history_repo"],
    )
    storefront_conversation_service = StorefrontConversationService(
        chat_service=chat_service,
        session_repo=repos["session_repo"],
        message_repo=repos["message_repo"],
        transfer_mgr=transfer_mgr,
    )
    wecom_order_lookup_service = WeComOrderLookupService(
        order_service=order_service,
        youzan_order_repo=repos.get("youzan_order_repo"),
        knowledge_retriever=employee_knowledge_retriever,
        youzan_client=youzan_client,
        config_repo=repos["config_repo"],
    )
    wecom_bot_business_tool_service = WeComBotBusinessToolService(
        order_service=order_service,
        order_lookup_service=wecom_order_lookup_service,
        catalog_service=catalog_service,
        knowledge_retriever=employee_knowledge_retriever,
    )
    wecom_bot_ops_tool_service = WeComBotOpsToolService(
        customer_address_service=customer_address_service,
        customer_group_service=customer_group_service,
        transfer_mgr=transfer_mgr,
    )
    wecom_bot_status_tool_service = WeComBotStatusToolService(
        observability_service=observability_service,
    )
    employee_agent_service = EmployeeAgentService(
        business_tool_service=wecom_bot_business_tool_service,
        ops_tool_service=wecom_bot_ops_tool_service,
        status_tool_service=wecom_bot_status_tool_service,
        order_lookup_service=wecom_order_lookup_service,
        trace_sink=trace_sink,
    )

    services = {
        "admin_service": admin_service,
        "knowledge_retriever": knowledge_retriever,
        "employee_knowledge_retriever": employee_knowledge_retriever,
        "observability_service": observability_service,
        **knowledge_services,
        "storefront_auth_service": storefront_auth_service,
        "catalog_service": catalog_service,
        "order_service": order_service,
        "stored_value_service": stored_value_service,
        "points_service": points_service,
        "coupon_service": coupon_service,
        "customer_address_service": customer_address_service,
        "customer_group_service": customer_group_service,
        "customer_consent_service": customer_consent_service,
        "privacy_lifecycle_service": privacy_lifecycle_service,
        "transfer_mgr": transfer_mgr,
        "shop_page_configuration_service": shop_page_configuration_service,
        "shop_configuration_service": shop_configuration_service,
        "youzan_client": youzan_client,
        "youzan_event_handler": youzan_event_handler,
        "reconcile_service": reconcile_service,
        "chat_service": chat_service,
        "storefront_conversation_service": storefront_conversation_service,
        "wecom_order_lookup_service": wecom_order_lookup_service,
        "wecom_bot_business_tool_service": wecom_bot_business_tool_service,
        "wecom_bot_ops_tool_service": wecom_bot_ops_tool_service,
        "wecom_bot_status_tool_service": wecom_bot_status_tool_service,
        "employee_agent_service": employee_agent_service,
    }
    return _with_legacy_service_aliases(services)


def _init_knowledge_management_services(
    repos: dict[str, Any],
    vs: Any,
) -> dict[str, Any]:
    """初始化后台知识治理和观测相关服务。"""
    from app.service.knowledge_admin import KnowledgeAdminService
    from app.service.knowledge_retrieval_report import KnowledgeRetrievalReportService
    from app.service.knowledge_sync import KnowledgeSyncService

    knowledge_sync_service = KnowledgeSyncService(
        knowledge_repo=repos["knowledge_repo"],
        history_repo=repos["history_repo"],
        embedding_searcher=vs,
    )
    return {
        "knowledge_sync_service": knowledge_sync_service,
        "knowledge_admin_service": KnowledgeAdminService(
            knowledge_repo=repos["knowledge_repo"],
            admin_repo=repos["knowledge_admin_repo"],
            history_repo=repos["history_repo"],
            sync_service=knowledge_sync_service,
        ),
        "knowledge_retrieval_report_service": KnowledgeRetrievalReportService(
            repos["knowledge_repo"]
        ),
    }


def _with_legacy_service_aliases(services: dict[str, Any]) -> dict[str, Any]:
    """补齐兼容期旧 service key，真实装配仍以 canonical key 为准。"""
    for legacy_key, canonical_key in LEGACY_SERVICE_ALIASES.items():
        services[legacy_key] = services[canonical_key]
    return services
