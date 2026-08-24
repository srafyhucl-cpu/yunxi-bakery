"""兼容入口：真实实现已迁移到 app.api.channels.router。"""

import sys

from app.api.channels import router as _module

sys.modules[__name__] = _module
