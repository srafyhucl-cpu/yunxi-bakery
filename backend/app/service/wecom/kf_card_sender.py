"""微信客服商品卡片发送。"""

from app.config import settings
from app.logger import setup_logger
from app.service.security.url_policy import fetch_limited_remote_image

logger = setup_logger()

IMAGE_FETCH_TIMEOUT_SECONDS = 10.0
MAX_CARD_IMAGE_BYTES = 5 * 1024 * 1024


async def send_kf_card(client, external_userid: str, card: dict) -> None:
    """发送商品 link 卡片，失败时降级为文本。"""
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

    result = await client.send_kf_link(
        external_userid=external_userid,
        title=title,
        url=link_url or "",
        desc=description,
        thumb_media_id=thumb_media_id or "",
    )
    if result.get("errcode") == 0:
        logger.info("客服商品卡片已发送 user=%s title=%s", external_userid, title)
        return

    logger.warning(
        "客服link卡片发送失败，降级为文本消息 user=%s err=%s",
        external_userid,
        result.get("errmsg"),
    )
    text_parts = [f"📦 {title}"]
    if price:
        text_parts.append(f"💰 ¥{price}")
    if link_url:
        text_parts.append(f"🔗 {link_url}")
    if img_url:
        text_parts.append(f"🖼️ {img_url}")

    text_result = await client.send_kf_text(external_userid, "\n".join(text_parts))
    if text_result.get("errcode") != 0:
        logger.error(
            "客服商品卡片文本降级也失败 user=%s err=%s",
            external_userid,
            text_result.get("errmsg"),
        )
