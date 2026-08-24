"""
配置管理。

使用 pydantic-settings 从 .env 文件和环境变量加载配置。
所有敏感信息（API Key、Secret）不进代码仓库。
"""

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"


def _read_version() -> str:
    """从项目根目录 VERSION 文件读取版本号，作为版本号的唯一来源。"""
    version_file = PROJECT_ROOT / "VERSION"
    return version_file.read_text(encoding="utf-8").strip()


APP_VERSION: str = _read_version()

RAG_RETRIEVAL_MODE_HYBRID = "hybrid"
RAG_RETRIEVAL_MODE_PLANNED_HYBRID = "planned-hybrid"
RAG_RETRIEVAL_MODE_PLANNED_HYBRID_RERANK = "planned-hybrid-rerank"
RAG_RETRIEVAL_MODES = frozenset(
    {
        RAG_RETRIEVAL_MODE_HYBRID,
        RAG_RETRIEVAL_MODE_PLANNED_HYBRID,
        RAG_RETRIEVAL_MODE_PLANNED_HYBRID_RERANK,
    }
)


class Settings(BaseSettings):
    """应用配置，字段默认值可被 .env 和环境变量覆盖。"""

    model_config = {
        "env_file": ENV_FILE,
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # .env 中未定义的额外字段忽略，不报错
    }

    # ── 服务配置 ──
    SERVER_HOST: str = "127.0.0.1"
    SERVER_PORT: int = 7001
    LOG_LEVEL: str = "info"

    # ── 数据库 ──
    DB_PATH: str = "data/bot.db"
    EMBEDDING_INDEX_DIR: str = "data/embeddings"
    ENABLE_HYBRID_RETRIEVAL: bool = False
    RAG_RETRIEVAL_MODE: str = RAG_RETRIEVAL_MODE_HYBRID
    RRF_K: int = 60
    ENABLE_CUSTOMER_MEMORY: bool = True
    ENABLE_OFFLINE_QA: bool = False
    ENABLE_OFFLINE_KNOWLEDGE_GAP: bool = False
    ENABLE_OFFLINE_MEMORY: bool = False
    LANGCHAIN_TRACING_ENABLED: bool = False
    LANGCHAIN_PROJECT: str = "yunxi-bakebot"
    LANGSMITH_API_KEY: str = ""
    AGENT_LOCAL_TRACE_ENABLED: bool = True
    AGENT_LOCAL_TRACE_PATH: str = ""
    ENABLE_REPLY_GUARD: bool = False
    ENABLE_OFFLINE_REVIEW: bool = False
    OFFLINE_REVIEW_NIGHT_START_HOUR: int = 22
    OFFLINE_REVIEW_NIGHT_END_HOUR: int = 6
    OFFLINE_REVIEW_INTERVAL_HOURS: float = 6.0
    OFFLINE_REVIEW_MAX_SESSIONS: int = 200
    SESSION_IDLE_CLOSE_MINUTES: int = 30
    SESSION_IDLE_CLOSE_SCAN_INTERVAL_SECONDS: int = 300

    # ── DeepSeek 大模型（已废弃，保留字段兼容） ──
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    # 视觉识别模型（已废弃，保留字段兼容）
    DEEPSEEK_VISION_MODEL: str = ""
    DEEPSEEK_TIMEOUT_SECONDS: float = 15.0

    # ── 小米 MiMo 大模型（主力 LLM） ──
    MIMO_API_KEY: str = ""
    MIMO_BASE_URL: str = "https://api.xiaomimimo.com/v1"
    # 文本对话模型
    MIMO_CHAT_MODEL: str = "mimo-v2.5"
    # 夜间沉淀可单独指定思考模型；未配置时回退到 MIMO_CHAT_MODEL
    MIMO_THINKING_MODEL: str = ""
    OFFLINE_REVIEW_MODEL: str = ""
    OFFLINE_MEMORY_MODEL: str = ""
    OFFLINE_KNOWLEDGE_GAP_MODEL: str = ""
    OFFLINE_LLM_REPAIR_RETRIES: int = 1
    # 视觉/多模态模型（支持图片输入）
    MIMO_VISION_MODEL: str = "mimo-v2.5"
    # 语音转文字模型（ASR）
    MIMO_ASR_MODEL: str = "mimo-v2.5-asr"
    MIMO_TIMEOUT_SECONDS: float = 120.0

    # ── 有赞云 ──
    YOUZAN_CLIENT_ID: str = ""
    YOUZAN_CLIENT_SECRET: str = ""
    YOUZAN_KDT_ID: str = ""
    YOUZAN_MOCK_MODE: bool = True
    YOUZAN_AUTH_URL: str = "https://open.youzanyun.com/auth/token"
    YOUZAN_API_BASE: str = "https://open.youzanyun.com/api"
    YOUZAN_GOODS_H5_BASE_URL: str = "https://h5.youzan.com/v2/showcase/goods"
    YOUZAN_HTTP_TIMEOUT_SECONDS: float = 10.0

    # ── 微信小程序 ──
    WECHAT_MINIAPP_APP_ID: str = ""
    WECHAT_MINIAPP_APP_SECRET: str = ""
    WECHAT_MINIAPP_AUTH_URL: str = "https://api.weixin.qq.com/sns/jscode2session"
    WECHAT_MINIAPP_HTTP_TIMEOUT_SECONDS: float = 10.0
    REMOTE_IMAGE_ALLOWED_HOSTS: str = "img.yzcdn.cn"
    STOREFRONT_AUTH_SECRET: str = ""
    STOREFRONT_AUTH_TTL_SECONDS: int = 3600
    STOREFRONT_AUTH_ALLOW_LEGACY_HEADER: bool = False
    ALLOW_MOCK_PAYMENT: bool = False
    # 积分余额权威来源：youzan=有赞 total 镜像，local=本地 member_balance.points
    POINTS_AUTHORITY: str = "youzan"
    # 券权威来源：youzan=有赞券镜像+本地核销（默认），local=本地自建发券核销
    COUPON_AUTHORITY: str = "youzan"
    WECHAT_PAY_ENABLED: bool = False
    WECHAT_PAY_API_BASE: str = "https://api.mch.weixin.qq.com"
    WECHAT_PAY_MCH_ID: str = ""
    WECHAT_PAY_NOTIFY_URL: str = ""
    WECHAT_PAY_PRIVATE_KEY_PATH: str = ""
    WECHAT_PAY_CERT_SERIAL_NO: str = ""
    WECHAT_PAY_PLATFORM_CERT_PATH: str = ""
    WECHAT_PAY_API_V3_KEY: str = ""
    MINIAPP_PAYMENT_TIMEOUT_SCAN_INTERVAL_SECONDS: int = 300

    # ── 管理后台 ──
    # 注意：生产环境必须在 .env 中设置强密码，不能使用默认值
    ADMIN_API_TOKEN: str = "CHANGE_ME_IN_PRODUCTION_ENV"
    ADMIN_SESSION_SECRET: str = ""
    ADMIN_SESSION_TTL_SECONDS: int = 1800
    ADMIN_ALLOW_LEGACY_BEARER: bool = False
    ADMIN_COOKIE_SECURE: bool = True
    ADMIN_ALLOWED_ORIGINS: str = ""
    ENABLE_API_DOCS: bool = False
    MAX_REQUEST_BODY_BYTES: int = 1_048_576
    MAX_CONCURRENT_REQUESTS: int = 100
    REQUEST_ACQUIRE_TIMEOUT_SECONDS: float = 0.2
    ADMIN_LOGIN_MAX_ATTEMPTS: int = 5
    ADMIN_LOGIN_WINDOW_SECONDS: int = 300
    REQUEST_RATE_LIMIT_MAX_REQUESTS: int = 300
    REQUEST_RATE_LIMIT_WINDOW_SECONDS: int = 60
    ADMIN_AI_FAILURE_THRESHOLD: int = 3
    ADMIN_AI_COOLDOWN_SECONDS: int = 60

    # ── 企业微信（客户联系） ──
    WECOM_CORP_ID: str = ""
    WECOM_AGENT_ID: str = ""
    WECOM_SECRET: str = ""
    WECOM_TOKEN: str = ""
    WECOM_ENCODING_AES_KEY: str = ""
    WECOM_STAFF_ID: str = ""  # 客服小李的企微 USER_ID
    WECOM_ROBOT_WEBHOOK: str = ""  # 企微值班群机器人 WEBHOOK 地址 (选填，支持群机器人)
    WECOM_BOT_PLUGIN_API_KEY: str = ""  # 企微智能机器人普通模式工具访问密钥
    WECOM_INTELLIGENT_BOT_TOKEN: str = ""  # 企微智能机器人 API URL 回调 Token
    WECOM_INTELLIGENT_BOT_ENCODING_AES_KEY: str = (
        ""  # 企微智能机器人 API URL 回调 AESKey
    )
    WECOM_EMPLOYEE_AUTH_REQUIRED: bool = False
    WECOM_EMPLOYEE_ALLOWED_USERS: str = ""
    WECOM_EMPLOYEE_ALLOWED_CHATS: str = ""
    WECOM_EMPLOYEE_CORP_ID: str = ""
    WECOM_EMPLOYEE_OPS_USERS: str = ""
    WECOM_CALLBACK_MAX_AGE_SECONDS: int = 300
    WECOM_CALLBACK_NONCE_CACHE_SIZE: int = 4096
    WECOM_API_BASE: str = "https://qyapi.weixin.qq.com/cgi-bin"
    WECOM_HTTP_TIMEOUT_SECONDS: float = 10.0
    # ── 企业微信（微信客服） ──
    # 微信客服与自建应用共用同一个回调URL / Token / EncodingAESKey
    # 只需额外配置客服账号 ID，用于发送消息时指定 open_kfid
    WECOM_KF_ID: str = ""  # 微信客服账号 ID (open_kfid)，格式如 wkxxxxxxxx
    WECOM_KF_SESSION_IDLE_CLOSE_SECONDS: int = 7200
    WECOM_KF_WELCOME_TEXT: str = "您好，我是芸熙烘焙智能助手，已接入为您继续服务。"
    WECOM_KF_SERVICER_USERID: str = (
        ""  # 转人工时的默认接待人员 userid（企微内部userid）
    )

    @field_validator("RAG_RETRIEVAL_MODE")
    @classmethod
    def validate_rag_retrieval_mode(cls, value: str) -> str:
        """校验 RAG 检索模式，避免生产误配到未知路径。"""
        normalized_value = value.strip().lower()
        if normalized_value not in RAG_RETRIEVAL_MODES:
            allowed_values = ", ".join(sorted(RAG_RETRIEVAL_MODES))
            raise ValueError(f"RAG_RETRIEVAL_MODE 只支持: {allowed_values}")
        return normalized_value


settings = Settings()
