"""上传图片真实性校验：魔数、分辩维度与像素预算，标准库实现。

不引入解码依赖：只解析容器头获取宽高并执行像素预算，
畸形与伪装文件在解码前拒绝；文件名由调用方生成不可控键。
"""

import struct

MAX_IMAGE_PIXELS = 16_777_216
MIN_IMAGE_DIMENSION = 1
MAX_IMAGE_DIMENSION = 16_384

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8\xff"
_RIFF_HEADER = b"RIFF"
_WEBP_MARK = b"WEBP"


def sniff_image_format(content: bytes) -> str:
    """识别图片容器格式，返回后缀或空字符串。"""
    if content.startswith(_PNG_SIGNATURE):
        return ".png"
    if content.startswith(_JPEG_SIGNATURE):
        return ".jpg"
    if (
        content.startswith(_RIFF_HEADER)
        and len(content) >= 12
        and content[8:12] == _WEBP_MARK
    ):
        return ".webp"
    return ""


def parse_image_dimensions(content: bytes, image_format: str) -> tuple[int, int]:
    """解析图片宽高，畸形结构直接抛出。"""
    if image_format == ".png":
        return _parse_png_dimensions(content)
    if image_format == ".jpg":
        return _parse_jpeg_dimensions(content)
    if image_format == ".webp":
        return _parse_webp_dimensions(content)
    raise ValueError(f"不支持的图片格式 {image_format}")


def validate_decoration_image(content: bytes, declared_suffix: str) -> tuple[int, int]:
    """校验声明类型与真实内容一致且维度合规，返回宽高。

    伪装扩展名、畸形文件、超大像素一律拒绝。
    """
    if not content:
        raise ValueError("图片文件不能为空")
    actual_format = sniff_image_format(content)
    if not actual_format:
        raise ValueError("无法识别的图片文件头")
    if actual_format != declared_suffix:
        raise ValueError(
            f"声明类型与真实内容不一致 declared={declared_suffix} actual={actual_format}"
        )
    width, height = parse_image_dimensions(content, actual_format)
    if not (
        MIN_IMAGE_DIMENSION <= width <= MAX_IMAGE_DIMENSION
        and MIN_IMAGE_DIMENSION <= height <= MAX_IMAGE_DIMENSION
    ):
        raise ValueError(f"图片尺寸越界 width={width} height={height}")
    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError(f"图片像素超预算 width={width} height={height}")
    return width, height


def _parse_png_dimensions(content: bytes) -> tuple[int, int]:
    """解析 PNG 首个 IHDR 块宽高。"""
    if len(content) < 33:
        raise ValueError("PNG 文件截断")
    if content[12:16] != b"IHDR":
        raise ValueError("PNG 缺少 IHDR 块")
    width, height = struct.unpack(">II", content[16:24])
    return int(width), int(height)


def _parse_jpeg_dimensions(content: bytes) -> tuple[int, int]:
    """扫描 JPEG 标记段，读取首个 SOF 帧尺寸。"""
    position = 2
    end = len(content)
    while position + 9 <= end:
        if content[position] != 0xFF:
            raise ValueError("JPEG 标记段损坏")
        marker = content[position + 1]
        if marker == 0xD8 or (0xD0 <= marker <= 0xD7) or marker == 0x01:
            position += 2
            continue
        if marker == 0xD9:
            break
        segment_length = struct.unpack(">H", content[position + 2 : position + 4])[0]
        if segment_length < 2 or position + segment_length > end:
            raise ValueError("JPEG 段长度越界")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            height, width = struct.unpack(">HH", content[position + 5 : position + 9])
            return int(width), int(height)
        position += 2 + segment_length
    raise ValueError("JPEG 未找到有效帧")


def _parse_webp_dimensions(content: bytes) -> tuple[int, int]:
    """解析 WEBP 容器宽高，覆盖 VP8/VP8L/VP8X。"""
    if len(content) < 30:
        raise ValueError("WEBP 文件截断")
    chunk = content[12:16]
    if chunk == b"VP8 ":
        if len(content) < 30:
            raise ValueError("WEBP VP8 帧头截断")
        width = struct.unpack("<H", content[26:28])[0] & 0x3FFF
        height = struct.unpack("<H", content[28:30])[0] & 0x3FFF
        return int(width), int(height)
    if chunk == b"VP8L":
        if len(content) < 25:
            raise ValueError("WEBP VP8L 帧头截断")
        bits = struct.unpack("<I", content[21:25])[0]
        return int(bits & 0x3FFF) + 1, int((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8X":
        if len(content) < 30:
            raise ValueError("WEBP VP8X 帧头截断")
        width = struct.unpack(">I", b"\x00" + content[24:27])[0] + 1
        height = struct.unpack(">I", b"\x00" + content[27:30])[0] + 1
        return int(width), int(height)
    raise ValueError("WEBP 不支持的块类型")
