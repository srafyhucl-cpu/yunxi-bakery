"""前台渠道公共常量。"""

# 兼容期内前台渠道仍复用微信小程序通道值，避免影响历史会话去重和外部契约。
STOREFRONT_CHANNEL = "wechat_miniapp"
STOREFRONT_DEMO_USER_ID = "miniapp-demo-user"
STOREFRONT_CHANNEL_MESSAGE_PREFIX = "miniapp"
DEFAULT_STOREFRONT_HUMAN_TRANSFER_REASON = "小程序用户主动请求人工客服"
