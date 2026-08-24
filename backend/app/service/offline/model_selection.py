"""离线沉淀模型选择。"""

from app.config import settings


def select_offline_review_model(explicit_model: str = "") -> str:
    """选择会话质检模型，优先使用离线专用模型。"""
    return _select_model(explicit_model, settings.OFFLINE_REVIEW_MODEL)


def select_offline_memory_model(explicit_model: str = "") -> str:
    """选择顾客画像沉淀模型，优先使用离线专用模型。"""
    return _select_model(explicit_model, settings.OFFLINE_MEMORY_MODEL)


def select_offline_gap_model(explicit_model: str = "") -> str:
    """选择知识缺口挖掘模型，优先使用离线专用模型。"""
    return _select_model(explicit_model, settings.OFFLINE_KNOWLEDGE_GAP_MODEL)


def _select_model(explicit_model: str, offline_model: str) -> str:
    return (
        explicit_model.strip()
        or offline_model.strip()
        or settings.MIMO_THINKING_MODEL.strip()
        or settings.MIMO_CHAT_MODEL
    )
