"""兼容入口：真实实现已迁移到 app.api.admin.dialog。"""

import sys

from app.api.admin import dialog as _module

sys.modules[__name__] = _module
