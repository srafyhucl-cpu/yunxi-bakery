-- 非空渠道消息键是跨进程幂等认领的全局唯一键。
CREATE UNIQUE INDEX IF NOT EXISTS uq_messages_channel_msg_id
ON messages(channel_msg_id)
WHERE channel_msg_id <> '';
