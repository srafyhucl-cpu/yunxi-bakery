"""lifespan 阶段 API 路由注册逻辑。

第一阶段平台化重组后，路由继续保留现有外部 path，
但装配时优先依赖 Platform 的 canonical 服务名。
"""

from typing import Any

from fastapi import FastAPI


def register_routes(app: FastAPI, services: dict[str, Any]) -> None:
    """注册所有 API 路由，并启动消息队列 Worker。"""
    from app.api.channels.storefront.addresses import (
        create_storefront_addresses_router,
    )
    from app.api.channels.storefront.auth import create_storefront_auth_router
    from app.api.channels.storefront.catalog import create_storefront_catalog_router
    from app.api.channels.storefront.chat import create_storefront_chat_router
    from app.api.channels.storefront.coupons import create_storefront_coupons_router
    from app.api.channels.storefront.group_registrations import (
        create_storefront_group_registrations_router,
    )
    from app.api.channels.storefront.orders import create_storefront_orders_router
    from app.api.channels.storefront.privacy import create_storefront_privacy_router
    from app.api.channels.storefront.payments import create_storefront_payments_router
    from app.api.channels.storefront.points import create_storefront_points_router
    from app.api.channels.storefront.recharges import (
        create_storefront_balance_router,
        create_storefront_recharges_router,
    )
    from app.api.integrations.wecom import router as wecom_router
    from app.api.integrations.wecom_intelligent_bot import (
        create_wecom_intelligent_bot_router,
    )
    from app.api.integrations.youzan_webhook import create_webhook_router
    from app.service.wecom.kf_message_queue import kf_queue
    from app.service.wecom.message_queue import wecom_queue

    wecom_queue.start_worker(services["chat_service"])
    kf_queue.start_worker(services["chat_service"])

    app.include_router(create_webhook_router(services["chat_service"]))
    _register_admin_shell_routes(app, services)
    app.include_router(
        create_storefront_auth_router(services["storefront_auth_service"])
    )
    app.include_router(
        create_storefront_addresses_router(services["customer_address_service"])
    )
    app.include_router(create_storefront_catalog_router(services["catalog_service"]))
    app.include_router(
        create_storefront_orders_router(
            services["order_service"],
            stored_value_service=services.get("stored_value_service"),
        )
    )
    app.include_router(
        create_storefront_privacy_router(
            services["customer_consent_service"],
            services.get("privacy_lifecycle_service"),
        )
    )
    app.include_router(create_storefront_payments_router(services["order_service"]))
    app.include_router(
        create_storefront_recharges_router(services["stored_value_service"])
    )
    app.include_router(
        create_storefront_balance_router(services["stored_value_service"])
    )
    app.include_router(create_storefront_points_router(services["points_service"]))
    app.include_router(create_storefront_coupons_router(services["coupon_service"]))
    app.include_router(
        create_storefront_chat_router(services["storefront_conversation_service"])
    )
    app.include_router(
        create_storefront_group_registrations_router(services["customer_group_service"])
    )
    _register_admin_operations_routes(app, services)
    app.include_router(
        create_wecom_intelligent_bot_router(
            tool_service=services["wecom_bot_business_tool_service"],
            ops_tool_service=services["wecom_bot_ops_tool_service"],
            status_tool_service=_with_offline_summary_provider(app, services),
            agent_service=services.get("employee_agent_service"),
        )
    )
    app.include_router(wecom_router)


def _register_admin_shell_routes(app: FastAPI, services: dict[str, Any]) -> None:
    """注册后台基础入口和通用配置路由。"""
    from app.api.admin import create_admin_router
    from app.api.admin.addresses import create_admin_addresses_router
    from app.api.admin.assets import create_admin_assets_router
    from app.api.admin.config import create_shop_config_router
    from app.api.admin.frontend import create_admin_frontend_router
    from app.api.admin.shop_pages import create_shop_page_config_router

    app.include_router(
        create_admin_router(
            chat_service=services["chat_service"],
            admin_service=services["admin_service"],
            transfer_mgr=services["transfer_mgr"],
        )
    )
    app.include_router(create_admin_frontend_router())
    app.include_router(create_admin_assets_router())
    app.include_router(create_shop_config_router(services["admin_service"]))
    app.include_router(
        create_shop_page_config_router(services["shop_page_configuration_service"])
    )
    app.include_router(
        create_admin_addresses_router(services["customer_address_service"])
    )


def _register_admin_operations_routes(app: FastAPI, services: dict[str, Any]) -> None:
    """注册后台业务运营路由。"""
    from app.api.admin.customer_groups import create_admin_customer_groups_router
    from app.api.admin.knowledge import create_admin_knowledge_router
    from app.api.admin.knowledge_retrieval_report import (
        create_admin_knowledge_retrieval_report_router,
    )
    from app.api.admin.observability import create_observability_router
    from app.api.admin.coupons import create_admin_coupons_router
    from app.api.admin.orders import create_admin_orders_router
    from app.api.admin.products import create_admin_products_router
    from app.service.coupon.admin import AdminCouponService

    app.include_router(create_admin_orders_router(services["order_service"]))
    app.include_router(
        create_admin_customer_groups_router(services["customer_group_service"])
    )
    app.include_router(
        create_admin_knowledge_router(services["knowledge_admin_service"])
    )
    app.include_router(
        create_admin_knowledge_retrieval_report_router(
            services["knowledge_retrieval_report_service"]
        )
    )
    app.include_router(create_observability_router(services["observability_service"]))
    app.include_router(
        create_admin_products_router(
            services["reconcile_service"],
            services["knowledge_sync_service"],
        )
    )
    app.include_router(create_admin_coupons_router(AdminCouponService()))


def _get_offline_review_summary(app: FastAPI) -> object | None:
    scheduler = getattr(app.state, "offline_review_scheduler", None)
    if scheduler is None:
        return None
    return scheduler.get_last_summary()


def _with_offline_summary_provider(
    app: FastAPI,
    services: dict[str, Any],
) -> Any:
    status_service = services["wecom_bot_status_tool_service"]
    status_service.set_offline_summary_provider(
        lambda: _get_offline_review_summary(app)
    )
    return status_service
