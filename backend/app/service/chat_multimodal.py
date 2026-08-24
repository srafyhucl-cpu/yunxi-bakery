"""ChatService 的多模态消息构造边界。"""

import base64

from app.logger import setup_logger

logger = setup_logger()

DEFAULT_IMAGE_MIME_TYPE = "image/jpeg"
PNG_SIGNATURE = b"\x89PNG"
JPEG_SIGNATURE = b"\xff\xd8"
WEBP_SIGNATURE = b"RIFF"
IMAGE_HEADER_SAMPLE_CHARS = 32
IMAGE_HEADER_BYTES = 4
IMAGE_EMPTY_TEXT = "[用户发送了一张图片]"
IMAGE_UNDERSTANDING_INSTRUCTION = (
    "请先观察这张图片，提取对烘焙客服有用的信息：主体/款式、文字、数量、颜色、"
    "尺寸线索、破损或异常、用户可能想解决的问题。"
    "如果无法确定，请明确说待确认，不要编造。然后结合用户文字回答。"
)


def normalize_image_data_uri(image_base64: str) -> str:
    if image_base64.startswith("data:"):
        return image_base64

    header_bytes = base64.b64decode(image_base64[:IMAGE_HEADER_SAMPLE_CHARS])[
        :IMAGE_HEADER_BYTES
    ]
    mime_type = DEFAULT_IMAGE_MIME_TYPE
    if header_bytes[:IMAGE_HEADER_BYTES] == PNG_SIGNATURE:
        mime_type = "image/png"
    elif header_bytes[0:2] == JPEG_SIGNATURE:
        mime_type = "image/jpeg"
    elif header_bytes[0:IMAGE_HEADER_BYTES] == WEBP_SIGNATURE:
        mime_type = "image/webp"
    return f"data:{mime_type};base64,{image_base64}"


def apply_multimodal_image_message(
    messages: list[dict],
    image_base64: str,
    session_id: str,
) -> None:
    image_data_uri = normalize_image_data_uri(image_base64)
    for index in range(len(messages) - 1, -1, -1):
        if messages[index].get("role") != "user":
            continue

        original_text = str(messages[index].get("content", "") or "").strip()
        text_prompt = (
            f"{IMAGE_UNDERSTANDING_INSTRUCTION}\n用户文字：{original_text}"
            if original_text
            else IMAGE_UNDERSTANDING_INSTRUCTION
        )
        messages[index] = {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": image_data_uri},
                },
                {
                    "type": "text",
                    "text": text_prompt or IMAGE_EMPTY_TEXT,
                },
            ],
        }
        logger.info(
            "会话 %s 已构建多模态消息（图片 %d 字符 base64）",
            session_id,
            len(image_base64),
        )
        return
