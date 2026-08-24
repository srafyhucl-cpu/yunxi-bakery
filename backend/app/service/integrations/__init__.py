"""第三方集成领域导出。"""

from app.service.integrations.wechat_pay import (
    WechatPayIntegrationService,
    WechatPayPrepayResult,
)

__all__ = ["WechatPayIntegrationService", "WechatPayPrepayResult"]
