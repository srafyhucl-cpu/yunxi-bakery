"""企业微信加解密（AES-256-CBC）。"""

import base64
import hashlib
import os
import struct

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


def _decode_aes_key(encoding_aes_key: str) -> bytes:
    """Base64 解码 EncodingAESKey 得到 AESKey（32 字节）。"""
    return base64.b64decode(encoding_aes_key + "=")


def decrypt(encoding_aes_key: str, msg_encrypt: str) -> str:
    """
    解密企微回调消息。

    参数：
        encoding_aes_key: 管理后台配置的 EncodingAESKey
        msg_encrypt: 回调 XML 中的 Encrypt 字段（Base64 字符串）
    返回：
        解密后的明文 XML 字符串
    """
    aes_key = _decode_aes_key(encoding_aes_key)
    iv = aes_key[:16]
    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    decryptor = cipher.decryptor()

    raw = base64.b64decode(msg_encrypt)
    decrypted = decryptor.update(raw) + decryptor.finalize()

    # PKCS7 去除填充
    unpadder = padding.PKCS7(256).unpadder()
    decrypted = unpadder.update(decrypted) + unpadder.finalize()

    # 格式：rand(16B) + msg_len(4B network order) + msg + corp_id
    msg_len = struct.unpack(">I", decrypted[16:20])[0]
    msg = decrypted[20 : 20 + msg_len]
    return msg.decode("utf-8")


def encrypt(encoding_aes_key: str, plaintext: str, corp_id: str) -> str:
    """
    加密回复消息（验证 URL 时需加密 echostr 并返回）。

    参数：
        encoding_aes_key: 管理后台配置的 EncodingAESKey
        plaintext: 待加密的文本
        corp_id: 接收方 ID；企业内部智能机器人场景传空字符串
    返回：
        Base64 编码的密文
    """
    aes_key = _decode_aes_key(encoding_aes_key)
    iv = aes_key[:16]

    plaintext_bytes = plaintext.encode("utf-8")
    raw = bytearray(os.urandom(16))
    raw.extend(struct.pack(">I", len(plaintext_bytes)))
    raw.extend(plaintext_bytes)
    raw.extend(corp_id.encode("utf-8"))

    # PKCS7 填充
    padder = padding.PKCS7(256).padder()
    padded = padder.update(bytes(raw)) + padder.finalize()

    cipher = Cipher(algorithms.AES(aes_key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("utf-8")


def verify_signature(
    token: str, timestamp: str, nonce: str, msg_encrypt: str, msg_signature: str
) -> bool:
    """
    验证企微回调签名。

    签名算法：SHA1(token + timestamp + nonce + msg_encrypt)
    """
    s = "".join(sorted([token, timestamp, nonce, msg_encrypt]))
    sig = hashlib.sha1(s.encode("utf-8")).hexdigest()
    return sig == msg_signature


def generate_signature(
    token: str,
    timestamp: str,
    nonce: str,
    msg_encrypt: str,
) -> str:
    """生成企微回调回复签名。"""
    return hashlib.sha1(
        "".join(sorted([token, timestamp, nonce, msg_encrypt])).encode("utf-8")
    ).hexdigest()
