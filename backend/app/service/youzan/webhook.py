"""
有赞 Webhook 工具函数集。

包含签名验证等通用逻辑。
"""

import hashlib
import hmac


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
