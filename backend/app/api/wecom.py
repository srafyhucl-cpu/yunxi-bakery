"""兼容入口：真实实现已迁移到 app.api.integrations.wecom。"""

import sys

from app.api.integrations import wecom as _module

sys.modules[__name__] = _module
