"""
应用异常层级。

所有业务异常继承自 AppError，方便 FastAPI 全局捕获后统一返回。
每个子类通过 status_code 类属性声明 HTTP 状态码，支持多态分发。
"""


class AppError(Exception):
    """应用异常基类，所有业务异常继承于此。"""

    status_code: int = 400


class AuthError(AppError):
    """认证失败：签名校验、Token 过期等。"""

    status_code: int = 403


class NotFoundError(AppError):
    """资源不存在：会话、消息、用户等查找不到。"""

    status_code: int = 404


class LLMError(AppError):
    """DeepSeek API 调用失败：网络超时、频率限制等。"""

    status_code: int = 502


class APIError(AppError):
    """外部 API 调用失败：有赞、企微接口异常。"""

    status_code: int = 502


class ConfigError(AppError):
    """配置错误：环境变量缺失、格式不正确等。"""

    status_code: int = 500
