"""
商品数据解析与同步通用工具。

将有赞 API 返回的原始商品数据解析为标准化字典，
并统一执行 youzan_products + knowledge_base + 向量索引的三表联写。

此模块提取自 event_item.py 和 function_tool_product.py 的重复逻辑（L-2.2），
是两个模块的共享底座。
"""

import json
import re

from app.logger import setup_logger
from app.models.content_change_history import WriteResult
from app.service.knowledge_admin import DEFAULT_PRIORITY
from app.service.youzan.event_item_parser import extract_item_tags
from app.service.youzan.product_rag_text import (
    build_product_embedding_text,
    build_product_rag_content,
)

logger = setup_logger()


def parse_product_from_api(raw_product: object, item_id: int) -> dict | None:
    """
    解析有赞 API 返回的商品原始数据。

    返回标准化字段字典，解析失败返回 None。
    """
    if not isinstance(raw_product, dict):
        return None
    outer = raw_product.get("data") or raw_product.get("response")
    if not isinstance(outer, dict) or "item" not in outer:
        return None

    item = outer["item"]
    if not isinstance(item, dict):
        return None
    title = item.get("title", "")
    alias = item.get("alias", "") or str(item_id)
    price_fen = item.get("price", 0)
    stock = item.get("quantity", 0)
    image = item.get("pic_url") or item.get("image") or ""
    skus = item.get("skus", [])
    item_props = item.get("item_props", [])
    tag_ids = [str(tag_id) for tag_id in item.get("tag_ids", []) if str(tag_id).strip()]
    sold_num = int(item.get("sold_num", 0) or 0)
    item_no = item.get("item_no", "") or ""

    raw_desc = item.get("desc", "") or item.get("summary", "") or ""
    desc_clean = re.sub(
        r"\s+", " ", re.sub(r"\n+", "\n", re.sub(r"<.*?>", "", raw_desc))
    ).strip()

    spec_names, prop_names, ingredients = extract_item_tags(
        title, skus, item_props, desc_clean
    )

    return {
        "item_id": item_id,
        "title": title,
        "alias": alias,
        "price_fen": price_fen,
        "stock": stock,
        "image": image,
        "skus": skus,
        "item_props": item_props,
        "tag_ids": tag_ids,
        "sold_num": sold_num,
        "item_no": item_no,
        "desc_clean": desc_clean,
        "spec_names": spec_names,
        "prop_names": prop_names,
        "ingredients": ingredients,
    }


def build_tags_str(parsed: dict, status_label: str) -> str:
    """构建商品标签字符串。"""
    return ", ".join(
        [status_label]
        + list(set(parsed["spec_names"]))
        + list(set(parsed["prop_names"]))
        + list(set(parsed["ingredients"]))
    )


async def sync_product_to_db(
    product_repo,
    parsed: dict,
    is_active: int,
    updated_at: str,
    tags_str: str,
    sync_source: str,
    sync_ref: str,
) -> str:
    """将解析后的商品数据写入 youzan_products 宽表。"""
    return await product_repo.upsert_product(
        item_id=parsed["item_id"],
        title=parsed["title"],
        alias=parsed["alias"],
        price_fen=parsed["price_fen"],
        stock=parsed["stock"],
        image=parsed["image"],
        is_active=is_active,
        updated_at=updated_at,
        skus_json=json.dumps(parsed["skus"], ensure_ascii=False),
        item_props_json=json.dumps(parsed["item_props"], ensure_ascii=False),
        desc=parsed["desc_clean"],
        tags=tags_str,
        tag_ids_json=json.dumps(parsed.get("tag_ids", []), ensure_ascii=False),
        sold_num=parsed["sold_num"],
        item_no=parsed["item_no"],
        sync_source=sync_source,
        sync_ref=sync_ref,
    )


async def sync_product_to_rag(
    knowledge_product_repo,
    embedding_searcher,
    parsed: dict,
    is_active: int,
    tags_str: str,
    status_label: str,
    updated_at: str,
    sync_source: str,
    sync_ref: str,
) -> str:
    """将商品同步到 RAG 知识库 + 向量索引。"""
    item_id = parsed["item_id"]
    title = parsed["title"]

    if is_active == 1:
        content_md = build_product_rag_content(
            title,
            parsed["alias"],
            status_label,
            parsed["skus"],
            parsed["item_props"],
            parsed["price_fen"],
            parsed["stock"],
            parsed["desc_clean"],
            tags_str,
            item_id=item_id,
            image=parsed["image"],
        )
        embedding_text = build_product_embedding_text(
            title,
            parsed["alias"],
            status_label,
            parsed["skus"],
            parsed["item_props"],
            parsed["price_fen"],
            parsed["desc_clean"],
            tags_str,
        )
        result = await knowledge_product_repo.upsert_product_knowledge(
            youzan_item_id=str(item_id),
            title=title,
            content=content_md,
            keywords=f"商品, 价格, 推荐, 蛋糕, {title}, {tags_str}",
            priority=DEFAULT_PRIORITY,
            updated_at=updated_at,
            sync_source=sync_source,
            sync_ref=sync_ref,
        )
        if result != WriteResult.APPLIED:
            return result
        if not await knowledge_product_repo.claim_product_vector_sync(
            str(item_id),
            updated_at,
        ):
            return WriteResult.SKIPPED
        try:
            if embedding_searcher is None:
                raise RuntimeError("向量索引服务不可用")
            vector = (
                embedding_searcher._get_model()
                .encode(
                    [embedding_text],
                    normalize_embeddings=True,
                )[0]
                .tolist()
            )
            await embedding_searcher.upsert_one(str(item_id), vector)
        except Exception as exc:
            logger.error("商品向量写入失败 item_id=%s err=%s", item_id, exc)
            marked_failed = (
                await knowledge_product_repo.mark_product_vector_sync_failed(
                    str(item_id),
                    updated_at,
                    str(exc),
                )
            )
            return WriteResult.FAILED if marked_failed else WriteResult.SKIPPED
        marked_success = await knowledge_product_repo.mark_product_vector_sync_success(
            str(item_id),
            updated_at,
        )
        return WriteResult.APPLIED if marked_success else WriteResult.SKIPPED

    result = await knowledge_product_repo.delete_product_knowledge(
        str(item_id),
        sync_source=sync_source,
        sync_ref=sync_ref,
    )
    if result != WriteResult.APPLIED:
        return result
    revision = await knowledge_product_repo.get_product_vector_revision(str(item_id))
    if not revision or not await knowledge_product_repo.claim_product_vector_sync(
        str(item_id),
        revision,
    ):
        return WriteResult.SKIPPED
    try:
        if embedding_searcher is None:
            raise RuntimeError("向量索引服务不可用")
        await embedding_searcher.delete_one(str(item_id))
    except Exception as exc:
        logger.error("商品向量删除失败 item_id=%s err=%s", item_id, exc)
        marked_failed = await knowledge_product_repo.mark_product_vector_sync_failed(
            str(item_id),
            revision,
            str(exc),
        )
        return WriteResult.FAILED if marked_failed else WriteResult.SKIPPED
    marked_success = await knowledge_product_repo.mark_product_vector_sync_success(
        str(item_id),
        revision,
    )
    return WriteResult.APPLIED if marked_success else WriteResult.SKIPPED
