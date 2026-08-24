from __future__ import annotations

import sys
import types
from typing import Any

from app import lifespan_routes, lifespan_services, main
from app.models.knowledge import KnowledgeAudience


class FakeApp:
    def __init__(self) -> None:
        self.included_routers: list[Any] = []
        self.state = types.SimpleNamespace()

    def include_router(self, router: Any) -> None:
        self.included_routers.append(router)


class FakeQueue:
    def __init__(self) -> None:
        self.started_with: list[Any] = []

    def start_worker(self, chat_service: Any) -> None:
        self.started_with.append(chat_service)


class FakeStatusToolService:
    def __init__(self) -> None:
        self.offline_summary_provider: Any = None

    def set_offline_summary_provider(self, provider: Any) -> None:
        self.offline_summary_provider = provider


def _install_module(monkeypatch: Any, name: str, **attrs: Any) -> None:
    module = types.ModuleType(name)
    if name in {"app.api.admin", "app.api.integrations"}:
        module.__path__ = []
    for key, value in attrs.items():
        setattr(module, key, value)
    monkeypatch.setitem(sys.modules, name, module)


def test_register_routes_starts_workers_and_includes_all_routers(
    monkeypatch,
) -> None:
    wecom_queue = FakeQueue()
    kf_queue = FakeQueue()
    _install_module(
        monkeypatch,
        "app.service.wecom.message_queue",
        wecom_queue=wecom_queue,
    )
    _install_module(
        monkeypatch,
        "app.service.wecom.kf_message_queue",
        kf_queue=kf_queue,
    )
    _install_module(
        monkeypatch,
        "app.api.admin",
        create_admin_router=lambda **kwargs: ("admin", kwargs),
    )
    _install_module(
        monkeypatch,
        "app.api.admin.addresses",
        create_admin_addresses_router=lambda service: ("admin-addresses", service),
    )
    _install_module(
        monkeypatch,
        "app.api.admin.assets",
        create_admin_assets_router=lambda: "admin-assets",
    )
    _install_module(
        monkeypatch,
        "app.api.admin.config",
        create_shop_config_router=lambda admin_service: ("config", admin_service),
    )
    _install_module(
        monkeypatch,
        "app.api.admin.customer_groups",
        create_admin_customer_groups_router=lambda service: (
            "admin-customer-groups",
            service,
        ),
    )
    _install_module(
        monkeypatch,
        "app.api.admin.frontend",
        create_admin_frontend_router=lambda: "frontend",
    )
    _install_module(
        monkeypatch,
        "app.api.admin.knowledge",
        create_admin_knowledge_router=lambda service: ("knowledge", service),
    )
    _install_module(
        monkeypatch,
        "app.api.admin.knowledge_retrieval_report",
        create_admin_knowledge_retrieval_report_router=lambda service: (
            "knowledge-retrieval-report",
            service,
        ),
    )
    _install_module(
        monkeypatch,
        "app.api.admin.observability",
        create_observability_router=lambda service: ("observability", service),
    )
    _install_module(
        monkeypatch,
        "app.api.admin.products",
        create_admin_products_router=lambda reconcile, sync: (
            "products",
            reconcile,
            sync,
        ),
    )
    _install_module(
        monkeypatch,
        "app.api.admin.coupons",
        create_admin_coupons_router=lambda service: ("admin-coupons", service),
    )
    _install_module(
        monkeypatch,
        "app.service.coupon.admin",
        AdminCouponService=lambda: "admin-coupon-service",
    )
    _install_module(
        monkeypatch,
        "app.api.admin.orders",
        create_admin_orders_router=lambda service: ("admin-orders", service),
    )
    _install_module(
        monkeypatch,
        "app.api.admin.shop_pages",
        create_shop_page_config_router=lambda service: ("shop-pages", service),
    )
    _install_module(
        monkeypatch,
        "app.api.channels.storefront.auth",
        create_storefront_auth_router=lambda service: ("miniapp-auth", service),
    )
    _install_module(
        monkeypatch,
        "app.api.channels.storefront.addresses",
        create_storefront_addresses_router=lambda service: (
            "miniapp-addresses",
            service,
        ),
    )
    _install_module(
        monkeypatch,
        "app.api.channels.storefront.catalog",
        create_storefront_catalog_router=lambda service: ("miniapp-catalog", service),
    )
    _install_module(
        monkeypatch,
        "app.api.channels.storefront.chat",
        create_storefront_chat_router=lambda service: ("miniapp-chat", service),
    )
    _install_module(
        monkeypatch,
        "app.api.channels.storefront.group_registrations",
        create_storefront_group_registrations_router=lambda service: (
            "miniapp-group-registrations",
            service,
        ),
    )
    _install_module(
        monkeypatch,
        "app.api.channels.storefront.orders",
        create_storefront_orders_router=lambda service, stored_value_service=None: (
            "miniapp-orders",
            service,
        ),
    )
    _install_module(
        monkeypatch,
        "app.api.channels.storefront.recharges",
        create_storefront_recharges_router=lambda service: (
            "miniapp-recharges",
            service,
        ),
        create_storefront_balance_router=lambda service: (
            "miniapp-balance",
            service,
        ),
    )
    _install_module(
        monkeypatch,
        "app.api.channels.storefront.privacy",
        create_storefront_privacy_router=lambda service, lifecycle_service=None: (
            "miniapp-privacy",
            service,
        ),
    )
    _install_module(
        monkeypatch,
        "app.api.channels.storefront.payments",
        create_storefront_payments_router=lambda service: (
            "miniapp-payments",
            service,
        ),
    )
    _install_module(
        monkeypatch,
        "app.api.channels.storefront.points",
        create_storefront_points_router=lambda service: (
            "miniapp-points",
            service,
        ),
    )
    _install_module(
        monkeypatch,
        "app.api.channels.storefront.coupons",
        create_storefront_coupons_router=lambda service: (
            "miniapp-coupons",
            service,
        ),
    )
    _install_module(
        monkeypatch,
        "app.api.integrations.youzan_webhook",
        create_webhook_router=lambda chat_service: ("webhook", chat_service),
    )
    _install_module(
        monkeypatch,
        "app.api.integrations.wecom_intelligent_bot",
        create_wecom_intelligent_bot_router=lambda **kwargs: (
            "wecom-intelligent-bot-router",
            kwargs,
        ),
    )
    _install_module(
        monkeypatch,
        "app.service.wecom.intelligent_bot_tools",
        WeComBotBusinessToolService=lambda **kwargs: (
            "wecom-business-tool-service",
            kwargs,
        ),
    )
    _install_module(
        monkeypatch,
        "app.service.wecom.intelligent_bot_ops_tools",
        WeComBotOpsToolService=lambda **kwargs: (
            "wecom-ops-tool-service",
            kwargs,
        ),
    )
    _install_module(
        monkeypatch,
        "app.service.wecom.intelligent_bot_status_tools",
        WeComBotStatusToolService=lambda **kwargs: (
            "wecom-status-tool-service",
            kwargs,
        ),
    )
    _install_module(monkeypatch, "app.api.integrations.wecom", router="wecom-router")
    app = FakeApp()
    status_tool_service = FakeStatusToolService()
    services = {
        "chat_service": "chat",
        "admin_service": "admin-service",
        "transfer_mgr": "transfer",
        "knowledge_admin_service": "knowledge-admin",
        "knowledge_retrieval_report_service": "knowledge-retrieval-report-service",
        "observability_service": "observability",
        "reconcile_service": "reconcile",
        "knowledge_sync_service": "knowledge-sync",
        "shop_page_configuration_service": "shop-pages-service",
        "storefront_auth_service": "storefront-auth-service",
        "customer_address_service": "customer-address-service",
        "catalog_service": "catalog-service",
        "order_service": "order-service",
        "stored_value_service": "stored-value-service",
        "points_service": "points-service",
        "coupon_service": "coupon-service",
        "knowledge_retriever": "knowledge-retriever",
        "storefront_conversation_service": "storefront-conversation-service",
        "customer_group_service": "customer-group-service",
        "customer_consent_service": "customer-consent-service",
        "wecom_bot_business_tool_service": "wecom-business-tool-service",
        "wecom_bot_ops_tool_service": "wecom-ops-tool-service",
        "wecom_bot_status_tool_service": status_tool_service,
        "employee_agent_service": "employee-agent-service",
    }

    lifespan_routes.register_routes(app, services)

    assert wecom_queue.started_with == ["chat"]
    assert kf_queue.started_with == ["chat"]
    assert len(app.included_routers) == 28
    assert app.included_routers[0] == ("webhook", "chat")
    wecom_router = app.included_routers[-2]
    assert wecom_router[0] == "wecom-intelligent-bot-router"
    assert wecom_router[1]["tool_service"] == "wecom-business-tool-service"
    assert wecom_router[1]["ops_tool_service"] == "wecom-ops-tool-service"
    assert wecom_router[1]["status_tool_service"] is status_tool_service
    assert wecom_router[1]["agent_service"] == "employee-agent-service"
    assert callable(status_tool_service.offline_summary_provider)
    assert app.included_routers[-1] == "wecom-router"


def test_init_services_wires_core_services(monkeypatch) -> None:
    created: dict[str, Any] = {}

    class FakeKnowledgeRetriever:
        def __init__(
            self,
            knowledge_repo,
            vs,
            *,
            config_repo,
            bm25,
            audience,
            youzan_product_repo,
        ) -> None:
            created.setdefault("knowledge_retrievers", []).append(
                (
                    knowledge_repo,
                    vs,
                    config_repo,
                    bm25,
                    audience,
                    self,
                )
            )

    class FakeYouzanClient:
        def __init__(self, *, config_repo) -> None:
            created["youzan_client"] = config_repo

    class FakeYouzanEventHandler:
        def __init__(self, **kwargs: Any) -> None:
            created["youzan_event_handler"] = kwargs

    class FakeProductReconcileService:
        def __init__(self, **kwargs: Any) -> None:
            created["reconcile_service"] = kwargs

    class FakeAdminService:
        def __init__(self, **kwargs: Any) -> None:
            created["admin_service"] = kwargs

    class FakeObservabilityService:
        def __init__(self, **kwargs: Any) -> None:
            created["observability_service"] = kwargs

    class FakeKnowledgeSyncService:
        def __init__(self, **kwargs: Any) -> None:
            created["knowledge_sync_service"] = kwargs

    class FakeKnowledgeAdminService:
        def __init__(self, **kwargs: Any) -> None:
            created["knowledge_admin_service"] = kwargs

    class FakeKnowledgeRetrievalReportService:
        def __init__(self, repo: Any) -> None:
            created["knowledge_retrieval_report_service"] = repo

    class FakeTransferManager:
        def __init__(self, repo: Any) -> None:
            created["transfer_mgr"] = repo

    class FakeStorefrontAuthService:
        def __init__(self) -> None:
            created["storefront_auth_service"] = True

    class FakeCustomerAddressService:
        def __init__(self, **kwargs: Any) -> None:
            created["customer_address_service"] = kwargs

    class FakeCustomerGroupOperationsService:
        def __init__(self, repo: Any) -> None:
            created["customer_group_service"] = repo

    class FakeCatalogApplicationService:
        def __init__(self, **kwargs: Any) -> None:
            created["catalog_service"] = kwargs

    class FakeOrderApplicationService:
        def __init__(self, **kwargs: Any) -> None:
            created["order_service"] = kwargs

    class FakeStoredValueService:
        def __init__(self) -> None:
            created["stored_value_service"] = True

    class FakePointsService:
        def __init__(self) -> None:
            created["points_service"] = True

    class FakeCouponService:
        def __init__(self) -> None:
            created["coupon_service"] = True

    class FakeStorefrontConversationService:
        def __init__(self, **kwargs: Any) -> None:
            created["storefront_conversation_service"] = kwargs

    class FakeWeComOrderLookupService:
        def __init__(self, **kwargs: Any) -> None:
            created["wecom_order_lookup_service"] = kwargs

    class FakeEmployeeAgentService:
        def __init__(self, **kwargs: Any) -> None:
            created["employee_agent_service"] = kwargs

    class FakeShopPageConfigurationService:
        def __init__(self, config_repo: Any) -> None:
            created["shop_page_configuration_service"] = config_repo

    class FakeShopConfigurationService:
        def __init__(self, config_repo: Any) -> None:
            created["shop_configuration_service"] = config_repo

    class FakeChatService:
        def __init__(self, **kwargs: Any) -> None:
            created["chat_service"] = kwargs

    monkeypatch.setattr(lifespan_services, "KnowledgeRetriever", FakeKnowledgeRetriever)
    monkeypatch.setattr(lifespan_services, "YouzanClient", FakeYouzanClient)
    monkeypatch.setattr(lifespan_services, "YouzanEventHandler", FakeYouzanEventHandler)
    monkeypatch.setattr(
        lifespan_services,
        "ProductReconcileService",
        FakeProductReconcileService,
    )
    monkeypatch.setattr(lifespan_services, "ChatService", FakeChatService)
    _install_module(monkeypatch, "app.service.admin", AdminService=FakeAdminService)
    _install_module(
        monkeypatch,
        "app.service.knowledge_admin",
        KnowledgeAdminService=FakeKnowledgeAdminService,
    )
    _install_module(
        monkeypatch,
        "app.service.knowledge_retrieval_report",
        KnowledgeRetrievalReportService=FakeKnowledgeRetrievalReportService,
    )
    _install_module(
        monkeypatch,
        "app.service.knowledge_sync",
        KnowledgeSyncService=FakeKnowledgeSyncService,
    )
    _install_module(
        monkeypatch,
        "app.service.channels.storefront",
        StorefrontAuthService=FakeStorefrontAuthService,
    )
    _install_module(
        monkeypatch,
        "app.service.customer",
        CustomerAddressService=FakeCustomerAddressService,
        CustomerGroupOperationsService=FakeCustomerGroupOperationsService,
    )
    _install_module(
        monkeypatch,
        "app.service.catalog",
        CatalogApplicationService=FakeCatalogApplicationService,
    )
    _install_module(
        monkeypatch,
        "app.service.order",
        OrderApplicationService=FakeOrderApplicationService,
    )
    _install_module(
        monkeypatch,
        "app.service.stored_value",
        StoredValueService=FakeStoredValueService,
    )
    _install_module(
        monkeypatch,
        "app.service.points",
        PointsService=FakePointsService,
    )
    _install_module(
        monkeypatch,
        "app.service.coupon",
        CouponService=FakeCouponService,
    )
    _install_module(
        monkeypatch,
        "app.service.conversation",
        StorefrontConversationService=FakeStorefrontConversationService,
    )
    _install_module(
        monkeypatch,
        "app.service.observability",
        ObservabilityService=FakeObservabilityService,
    )
    _install_module(
        monkeypatch,
        "app.service.ops",
        ShopPageConfigurationService=FakeShopPageConfigurationService,
        ShopConfigurationService=FakeShopConfigurationService,
    )
    _install_module(
        monkeypatch,
        "app.service.transfer_manager",
        TransferManager=FakeTransferManager,
    )
    _install_module(
        monkeypatch,
        "app.service.wecom.intelligent_bot_order_lookup",
        WeComOrderLookupService=FakeWeComOrderLookupService,
    )
    _install_module(
        monkeypatch,
        "app.service.wecom.employee_agent_service",
        EmployeeAgentService=FakeEmployeeAgentService,
    )
    repos = {
        "session_repo": "session-repo",
        "message_repo": "message-repo",
        "knowledge_repo": "knowledge-repo",
        "knowledge_admin_repo": "knowledge-admin-repo",
        "knowledge_product_repo": "knowledge-product-repo",
        "transfer_repo": "transfer-repo",
        "config_repo": "config-repo",
        "history_repo": "history-repo",
        "youzan_product_repo": "youzan-product-repo",
        "youzan_order_repo": "youzan-order-repo",
        "youzan_inventory_repo": "youzan-inventory-repo",
        "order_repo": "order-repo",
        "order_event_repo": "order-event-repo",
        "customer_address_repo": "customer-address-repo",
        "customer_address_audit_repo": "customer-address-audit-repo",
        "customer_group_repo": "customer-group-repo",
        "miniapp_address_repo": "miniapp-address-repo",
        "miniapp_address_audit_repo": "miniapp-address-audit-repo",
        "webhook_event_repo": "webhook-event-repo",
        "analytics_repo": "analytics-repo",
        "customer_profile_repo": "customer-profile-repo",
        "conversation_summary_repo": "conversation-summary-repo",
    }

    services = lifespan_services.init_services(repos, vs="vector", bm25="bm25")

    assert set(services) == {
        "admin_service",
        "knowledge_retriever",
        "employee_knowledge_retriever",
        "observability_service",
        "knowledge_sync_service",
        "knowledge_admin_service",
        "knowledge_retrieval_report_service",
        "storefront_auth_service",
        "customer_address_service",
        "customer_group_service",
        "customer_consent_service",
        "privacy_lifecycle_service",
        "catalog_service",
        "order_service",
        "stored_value_service",
        "points_service",
        "coupon_service",
        "storefront_conversation_service",
        "wecom_order_lookup_service",
        "transfer_mgr",
        "shop_page_configuration_service",
        "shop_configuration_service",
        "wecom_bot_business_tool_service",
        "wecom_bot_ops_tool_service",
        "wecom_bot_status_tool_service",
        "employee_agent_service",
        "youzan_client",
        "youzan_event_handler",
        "reconcile_service",
        "chat_service",
        "miniapp_auth_service",
        "miniapp_address_service",
        "miniapp_catalog_service",
        "miniapp_order_service",
        "miniapp_chat_service",
        "shop_page_config_service",
    }
    created_retrievers = created["knowledge_retrievers"]
    assert [item[:5] for item in created_retrievers] == [
        (
            "knowledge-repo",
            "vector",
            "config-repo",
            "bm25",
            KnowledgeAudience.CUSTOMER.value,
        ),
        (
            "knowledge-repo",
            "vector",
            "config-repo",
            "bm25",
            KnowledgeAudience.EMPLOYEE.value,
        ),
    ]
    assert services["knowledge_retriever"] is created_retrievers[0][5]
    assert services["employee_knowledge_retriever"] is created_retrievers[1][5]
    assert services["knowledge_retriever"] is not None
    assert created["transfer_mgr"] == "transfer-repo"
    assert created["chat_service"]["youzan_client"] is services["youzan_client"]
    assert (
        created["chat_service"]["knowledge_retriever"]
        is services["knowledge_retriever"]
    )
    assert (
        created["youzan_event_handler"]["knowledge_retriever"]
        is services["knowledge_retriever"]
    )
    assert created["chat_service"]["customer_profile_repo"] == "customer-profile-repo"
    assert (
        created["chat_service"]["conversation_summary_repo"]
        == "conversation-summary-repo"
    )
    assert created["order_service"]["order_repo"] == "order-repo"
    assert created["wecom_order_lookup_service"] == {
        "order_service": services["order_service"],
        "youzan_order_repo": "youzan-order-repo",
        "knowledge_retriever": services["employee_knowledge_retriever"],
        "youzan_client": services["youzan_client"],
        "config_repo": "config-repo",
    }
    assert created["employee_agent_service"] == {
        "business_tool_service": services["wecom_bot_business_tool_service"],
        "ops_tool_service": services["wecom_bot_ops_tool_service"],
        "status_tool_service": services["wecom_bot_status_tool_service"],
        "order_lookup_service": services["wecom_order_lookup_service"],
        "trace_sink": None,
    }
    assert created["order_service"]["event_repo"] == "order-event-repo"
    assert (
        created["customer_address_service"]["address_repo"] == "customer-address-repo"
    )
    assert (
        created["customer_address_service"]["audit_repo"]
        == "customer-address-audit-repo"
    )
    assert created["customer_group_service"] == "customer-group-repo"
    assert (
        created["storefront_conversation_service"]["chat_service"]
        is services["chat_service"]
    )
    assert (
        created["storefront_conversation_service"]["transfer_mgr"]
        is services["transfer_mgr"]
    )
    assert services["miniapp_auth_service"] is services["storefront_auth_service"]
    assert services["miniapp_catalog_service"] is services["catalog_service"]
    assert services["miniapp_order_service"] is services["order_service"]
    assert services["miniapp_address_service"] is services["customer_address_service"]
    assert (
        services["miniapp_chat_service"] is services["storefront_conversation_service"]
    )
    assert (
        services["shop_page_config_service"]
        is services["shop_page_configuration_service"]
    )
    assert created["shop_page_configuration_service"] == "config-repo"
    assert (
        created["reconcile_service"]["knowledge_product_repo"]
        == "knowledge-product-repo"
    )
    assert created["knowledge_retrieval_report_service"] == "knowledge-repo"


def test_legacy_repository_aliases_point_to_canonical_repositories() -> None:
    repos = {
        "customer_address_repo": object(),
        "customer_address_audit_repo": object(),
    }

    result = main._with_legacy_repository_aliases(repos)

    assert result["miniapp_address_repo"] is result["customer_address_repo"]
    assert result["miniapp_address_audit_repo"] is result["customer_address_audit_repo"]
