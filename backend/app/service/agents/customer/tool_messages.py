"""客户机器人工具运行上下文。"""

from dataclasses import dataclass
from typing import Any

from app.models.session import Session


@dataclass(frozen=True)
class ToolExecutionContext:
    """客户工具执行所需上下文。"""

    session: Session
    history_text: str
    transfer_mgr: Any
    session_repo: Any
    knowledge: Any
    youzan_client: Any
    order_repo: Any = None
    config_repo: Any = None
    product_repo: Any = None
    knowledge_product_repo: Any = None
    analytics_repo: Any = None
    history_repo: Any = None
    embedding_searcher: Any = None
