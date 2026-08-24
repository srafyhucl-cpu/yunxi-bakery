"""兼容入口：真实实现已迁移到 app.api.admin.shop_pages。"""

import sys

from app.api.admin import shop_pages as _module

sys.modules[__name__] = _module
