"""
有赞 Webhook 工具函数集。

包含签名验证、消息解析、item_id 多级降级提取等通用逻辑。
"""

import hashlib
import hmac
import json

from app.exceptions import AuthError
from app.logger import setup_logger

logger = setup_logger()


def verify_signature(
    client_id: str, client_secret: str, raw_body: bytes, signature_header: str
) -> bool:
    """验证有赞消息推送签名：MD5(client_id + raw_body + client_secret)。"""
    expected = hashlib.md5(
        (
            client_id + raw_body.decode("utf-8", errors="replace") + client_secret
        ).encode()
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)


def parse_webhook_payload(body: bytes) -> dict:
    """解析 webhook JSON 负载，解析失败抛出 AuthError。"""
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        logger.error("Invalid Youzan webhook payload: %s", exc)
        raise AuthError("Invalid JSON payload") from exc
