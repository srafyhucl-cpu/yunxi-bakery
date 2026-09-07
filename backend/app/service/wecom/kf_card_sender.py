"""微信客服商品卡片发送。"""

from app.config import settings
from app.logger import setup_logger
from app.service.security.url_policy import fetch_limited_remote_image

logger = setup_logger()

IMAGE_FETCH_TIMEOUT_SECONDS = 10.0
MAX_CARD_IMAGE_BYTES = 5 * 1024 * 1024


async def send_kf_card(
    client,
    external_userid: str,
    card: dict,
    db=None,
    inbound_msg_id: str = "",
    part: str = "card",
    open_kfid: str = "",
) -> str:
    """发送商品 link 卡片，失败时降级为文本。

    全部发送统一经过幂等投递账本；缺少投递上下文直接拒绝，不再直发，
    防止重复回复与未知结果无法追踪。
    """
    if not inbound_msg_id:
        raise ValueError("发送商品卡片缺少入站幂等标识，拒绝直发")
    title = card.get("title", "商品推荐")
    price = card.get("price", "")
    img_url = card.get("src", "")
    link_url = card.get("url", "")
    description = f"¥{price}" if price else title
    thumb_media_id = ""

    if img_url:
        try:
            image = await fetch_limited_remote_image(
                img_url,
                allowed_hosts=settings.REMOTE_IMAGE_ALLOWED_HOSTS.split(","),
                timeout_seconds=IMAGE_FETCH_TIMEOUT_SECONDS,
                max_bytes=MAX_CARD_IMAGE_BYTES,
            )
            if image is not None:
                img_data, _content_type = image
                logger.info("已通过安全策略下载商品图片 size=%dB", len(img_data))
                thumb_media_id = await client.upload_kf_temp_media(
                    file_data=img_data,
                    file_type="image",
                    file_name=f"{title}.jpg",
                )
            else:
                logger.warning("商品图片未通过下载安全策略")
        except Exception as exc:
            logger.warning("下载/上传商品图片异常 err=%s", exc)

    result = await _send_link(
        client,
        external_userid,
        title,
        link_url,
        description,
        thumb_media_id,
        db,
        inbound_msg_id,
        part,
        open_kfid,
    )
    if result == "sent":
        logger.info("客服商品卡片已发送 user=%s title=%s", external_userid, title)
        return result
    if result == "unknown":
        logger.warning(
            "客服商品卡片结果未知 user=%s title=%s，转人工确认", external_userid, title
        )
        return result

    logger.warning(
        "客服link卡片发送失败，降级为文本消息 user=%s err=%s",
        external_userid,
        result,
    )
    text_parts = [f"📦 {title}"]
    if price:
        text_parts.append(f"💰 ¥{price}")
    if link_url:
        text_parts.append(f"🔗 {link_url}")
    if img_url:
        text_parts.append(f"🖼️ {img_url}")

    fallback_text = "\n".join(text_parts)
    from app.service.wecom.kf_outbound_sender import send_text_guarded

    return await send_text_guarded(
        client,
        external_userid,
        inbound_msg_id,
        fallback_text,
        part=f"{part}-fallback",
        open_kfid=open_kfid,
    )


async def _send_link(
    client,
    external_userid: str,
    title: str,
    link_url: str,
    description: str,
    thumb_media_id: str,
    db,
    inbound_msg_id: str,
    part: str,
    open_kfid: str,
) -> str:
    """统一经幂等投递账本发送图文链接，不再保留直发分支。"""
    from app.service.wecom.kf_outbound_sender import send_link_guarded

    return await send_link_guarded(
        client,
        external_userid,
        inbound_msg_id,
        title,
        link_url or "",
        desc=description,
        thumb_media_id=thumb_media_id or "",
        part=part,
        open_kfid=open_kfid,
    )
