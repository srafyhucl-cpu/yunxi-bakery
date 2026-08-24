"""兼容入口：真实实现已迁移到 app.api.integrations.youzan_webhook。"""

import sys

from app.api.integrations import youzan_webhook as _module

sys.modules[__name__] = _module
