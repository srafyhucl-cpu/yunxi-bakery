"""兼容入口：真实实现已迁移到 app.api.integrations.webhook_helpers。"""

import sys

from app.api.integrations import webhook_helpers as _module

sys.modules[__name__] = _module
