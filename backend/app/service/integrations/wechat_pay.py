"""微信支付第三方适配。"""

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from hmac import compare_digest
from pathlib import Path

import httpx

from app.config import settings

PAYMENT_SIGN_TYPE = "RSA"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"
WECHAT_PAY_SUCCESS_STATE = "SUCCESS"
WECHAT_JSAPI_REQUEST_PATH = "/v3/pay/transactions/jsapi"


@dataclass(frozen=True)
class WechatPayPrepayResult:
    """微信支付预下单结果。"""

    prepay_id: str
    appid: str


class WechatPayIntegrationService:
    """封装微信支付第三方协议细节。"""

    def is_ready(self) -> bool:
        """检查微信支付配置是否齐备。"""
        return bool(
            settings.WECHAT_PAY_ENABLED
            and settings.WECHAT_MINIAPP_APP_ID
            and settings.WECHAT_PAY_MCH_ID
            and settings.WECHAT_PAY_NOTIFY_URL
            and settings.WECHAT_PAY_PRIVATE_KEY_PATH
            and settings.WECHAT_PAY_CERT_SERIAL_NO
            and settings.WECHAT_PAY_API_V3_KEY
        )

    def verify_notify_signature(self, raw_body: bytes, headers: dict[str, str]) -> bool:
        """校验微信支付通知签名。"""
        if not settings.WECHAT_PAY_PLATFORM_CERT_PATH:
            return False
        timestamp = headers.get("wechatpay-timestamp", "")
        nonce = headers.get("wechatpay-nonce", "")
        signature = headers.get("wechatpay-signature", "")
        serial = headers.get("wechatpay-serial", "")
        if not timestamp or not nonce or not signature or not serial:
            return False
        cert_path = Path(settings.WECHAT_PAY_PLATFORM_CERT_PATH)
        if not cert_path.exists():
            return False
        message = b"\n".join(
            [timestamp.encode("utf-8"), nonce.encode("utf-8"), raw_body, b""]
        )
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes
            from cryptography.hazmat.primitives.asymmetric import padding

            cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
            cert.public_key().verify(
                base64.b64decode(signature),
                message,
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except Exception:
            return False
        expected_serial = (
            cert.serial_number.to_bytes(
                (cert.serial_number.bit_length() + 7) // 8,
                "big",
            )
            .hex()
            .upper()
        )
        return compare_digest(expected_serial, serial.upper())

    def decrypt_notify_resource(self, resource: dict) -> dict:
        """解密微信支付通知资源。"""
        ciphertext = str(resource.get("ciphertext", ""))
        nonce = str(resource.get("nonce", ""))
        associated_data = str(resource.get("associated_data", ""))
        if not ciphertext or not nonce:
            raise ValueError("微信支付通知 resource 无效")
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            aesgcm = AESGCM(settings.WECHAT_PAY_API_V3_KEY.encode("utf-8"))
            plaintext = aesgcm.decrypt(
                nonce.encode("utf-8"),
                base64.b64decode(ciphertext),
                associated_data.encode("utf-8"),
            )
        except Exception as exc:
            raise ValueError("微信支付通知解密失败") from exc
        try:
            value = json.loads(plaintext.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("微信支付通知 JSON 无效") from exc
        if not isinstance(value, dict):
            raise ValueError("微信支付通知 JSON 无效")
        return value

    def format_success_time(self, value: str) -> str:
        """格式化微信支付成功时间。"""
        text = value.strip()
        if not text:
            return datetime.now().strftime(TIME_FORMAT)
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now().strftime(TIME_FORMAT)
        return parsed.strftime(TIME_FORMAT)

    async def create_jsapi_prepay(
        self,
        *,
        order_id: str,
        total_fen: int,
        description: str,
        payer_openid: str,
    ) -> WechatPayPrepayResult:
        """调用微信支付 API v3 JSAPI 下单。"""
        body = {
            "appid": settings.WECHAT_MINIAPP_APP_ID,
            "mchid": settings.WECHAT_PAY_MCH_ID,
            "description": description,
            "out_trade_no": order_id,
            "notify_url": settings.WECHAT_PAY_NOTIFY_URL,
            "amount": {"total": total_fen, "currency": "CNY"},
            "payer": {"openid": payer_openid},
        }
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":"))
        auth_header = self._build_wechat_auth_header(
            "POST",
            WECHAT_JSAPI_REQUEST_PATH,
            payload,
        )
        async with httpx.AsyncClient(
            timeout=settings.WECHAT_MINIAPP_HTTP_TIMEOUT_SECONDS,
            trust_env=False,
        ) as client:
            response = await client.post(
                f"{settings.WECHAT_PAY_API_BASE.rstrip('/')}{WECHAT_JSAPI_REQUEST_PATH}",
                headers={
                    "Authorization": auth_header,
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                content=payload.encode("utf-8"),
            )
            response.raise_for_status()
            data = response.json()
        prepay_id = str(data.get("prepay_id", "")).strip()
        if not prepay_id:
            raise ValueError("微信支付预下单失败")
        return WechatPayPrepayResult(
            prepay_id=prepay_id,
            appid=settings.WECHAT_MINIAPP_APP_ID,
        )

    def build_payment_params(
        self,
        prepay_id: str,
        *,
        signer: Callable[[str], str],
    ) -> dict:
        """构造小程序调起支付所需参数。"""
        timestamp = str(int(datetime.now().timestamp()))
        nonce_str = sha256(f"{prepay_id}:{timestamp}".encode("utf-8")).hexdigest()[:32]
        package = f"prepay_id={prepay_id}"
        message = "\n".join(
            [
                settings.WECHAT_MINIAPP_APP_ID,
                timestamp,
                nonce_str,
                package,
                "",
            ]
        )
        sign = signer(message)
        return {
            "timeStamp": timestamp,
            "nonceStr": nonce_str,
            "package": package,
            "signType": PAYMENT_SIGN_TYPE,
            "paySign": sign,
        }

    def sign_with_rsa(self, message: str) -> str:
        """使用商户私钥对微信支付消息签名。"""
        private_key_path = Path(settings.WECHAT_PAY_PRIVATE_KEY_PATH)
        if not private_key_path.exists():
            raise ValueError("微信支付私钥文件不存在")
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding
        except Exception as exc:  # pragma: no cover - 依赖缺失时明确报错
            raise ValueError("微信支付签名依赖不可用") from exc
        private_key = serialization.load_pem_private_key(
            private_key_path.read_bytes(),
            password=None,
        )
        signature = private_key.sign(
            message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode("utf-8")

    def _build_wechat_auth_header(
        self,
        method: str,
        request_path: str,
        body: str,
    ) -> str:
        timestamp = str(int(datetime.now().timestamp()))
        nonce_str = sha256(
            f"{timestamp}:{request_path}:{body}".encode("utf-8")
        ).hexdigest()[:32]
        message = "\n".join(
            [method.upper(), request_path, timestamp, nonce_str, body, ""]
        )
        signature = self.sign_with_rsa(message)
        return (
            "WECHATPAY2-SHA256-RSA2048 "
            f'mchid="{settings.WECHAT_PAY_MCH_ID}",'
            f'nonce_str="{nonce_str}",'
            f'timestamp="{timestamp}",'
            f'serial_no="{settings.WECHAT_PAY_CERT_SERIAL_NO}",'
            f'signature="{signature}"'
        )


__all__ = [
    "PAYMENT_SIGN_TYPE",
    "TIME_FORMAT",
    "WECHAT_PAY_SUCCESS_STATE",
    "WechatPayIntegrationService",
    "WechatPayPrepayResult",
    "settings",
]
