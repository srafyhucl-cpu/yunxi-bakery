"""知识检索结果的商品实时数据增强。"""

import urllib.parse

from app.logger import setup_logger
from app.models.knowledge import KnowledgeEntry
from app.repository.knowledge_repo import KnowledgeRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.youzan.client import YOUZAN_GOODS_H5_BASE_URL

logger = setup_logger()

RECOMMENDABLE_PRODUCT_ACTIVE = 1
MIN_RECOMMENDABLE_STOCK = 1
# 虚拟高库存阈值（生日/定制蛋糕类设置为 >= 此值表示常态化可下单）
VIRTUAL_HIGH_STOCK_THRESHOLD = 200


async def prepend_live_data(
    repo: KnowledgeRepo,
    entries: list[KnowledgeEntry],
    product_repo: YouzanProductRepo | None = None,
) -> list[KnowledgeEntry]:
    """对于商品知识条目，拼接实时库存、售价和 UMP 标记。"""
    if not entries:
        return entries

    if product_repo is None:
        return entries
    for entry in entries:
        if not entry.youzan_item_id:
            continue
        try:
            product = await product_repo.get_by_id(int(entry.youzan_item_id))
            if product:
                _prepend_product_content(entry, product)
        except Exception as exc:
            logger.warning(
                "现场反查商品库存（ID: %s）发生非致命异常: %s",
                entry.youzan_item_id,
                exc,
            )
    return entries


async def filter_recommendable_featured_products(
    repo: KnowledgeRepo,
    entries: list[KnowledgeEntry],
    product_repo: YouzanProductRepo | None = None,
) -> list[KnowledgeEntry]:
    """保留已上架且有库存的后台主推商品知识。"""
    if not entries:
        return []

    if product_repo is None:
        return []
    recommendable_entries: list[KnowledgeEntry] = []
    for entry in entries:
        if not entry.youzan_item_id:
            logger.warning("后台主推款缺少有赞商品ID，已跳过: %s", entry.title)
            continue
        try:
            product = await product_repo.get_by_id(int(entry.youzan_item_id))
        except (TypeError, ValueError) as exc:
            logger.warning(
                "后台主推款有赞商品ID无效，已跳过: title=%s id=%s err=%s",
                entry.title,
                entry.youzan_item_id,
                exc,
            )
            continue
        if _is_recommendable_product(entry, product):
            recommendable_entries.append(entry)
    return recommendable_entries


def _prepend_product_content(entry: KnowledgeEntry, product: object) -> None:
    price_yuan = product["price_fen"] / 100.0
    stock = product["stock"]
    is_active = product["is_active"]
    entry.content = _build_live_prefix(price_yuan, stock, is_active) + entry.content
    if is_active == RECOMMENDABLE_PRODUCT_ACTIVE:
        entry.content += _build_ump_tags(entry, product, price_yuan)


def _build_live_prefix(price_yuan: float, stock: int, is_active: int) -> str:
    if is_active == 0:
        return "【芸熙烘焙小程序实时官方数据 — ⚠️商品当前已下架或暂停预定】\n\n"
    if stock <= 0:
        return f"【芸熙烘焙小程序实时官方数据 — 当前售价：{price_yuan:.2f}元 | ⚠️商品当前在售但库存已为0，暂无现货，需要提前预约】\n\n"
    if stock >= VIRTUAL_HIGH_STOCK_THRESHOLD:
        return f"【芸熙烘焙小程序实时官方数据 — 当前售价：{price_yuan:.2f}元 | 实时可用库存：充足（常态化现做预定制商品，只要买家下单即可新鲜现做，请告知买家随时可放心下单，无需向其透露具体数字）】\n\n"
    return f"【芸熙烘焙小程序实时官方数据 — 当前售价：{price_yuan:.2f}元 | 实时可用库存：仅剩 {stock} 件（属于每日限量现烤面包西点，售罄即止，若库存偏低请温和提示买家抢购）】\n\n"


def _build_ump_tags(entry: KnowledgeEntry, product: object, price_yuan: float) -> str:
    alias = product["alias"] or ""
    image = product["image"] or ""
    img_params = urllib.parse.urlencode(
        {"type": "image", "src": image},
        quote_via=urllib.parse.quote,
    )
    card_params = urllib.parse.urlencode(
        {
            "type": "card",
            "id": entry.youzan_item_id,
            "title": entry.title,
            "price": f"{price_yuan:.2f}",
            "src": image,
            "url": f"{YOUZAN_GOODS_H5_BASE_URL}?alias={alias}",
        },
        quote_via=urllib.parse.quote,
    )
    return f"\n[UMP: {img_params}]\n[UMP: {card_params}]"


def _is_recommendable_product(entry: KnowledgeEntry, product: object) -> bool:
    if not product:
        logger.warning(
            "后台主推款未找到有赞商品物理数据，已跳过: title=%s id=%s",
            entry.title,
            entry.youzan_item_id,
        )
        return False
    if product["is_active"] != RECOMMENDABLE_PRODUCT_ACTIVE:
        logger.warning(
            "后台主推款商品未上架，已跳过: title=%s id=%s",
            entry.title,
            entry.youzan_item_id,
        )
        return False
    if product["stock"] < MIN_RECOMMENDABLE_STOCK:
        logger.warning(
            "后台主推款商品库存不足，已跳过: title=%s id=%s stock=%s",
            entry.title,
            entry.youzan_item_id,
            product["stock"],
        )
        return False
    return True
