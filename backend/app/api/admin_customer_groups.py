"""兼容入口：真实实现已迁移到 app.api.admin.customer_groups。"""

import sys

from app.api.admin import customer_groups as _module

sys.modules[__name__] = _module
