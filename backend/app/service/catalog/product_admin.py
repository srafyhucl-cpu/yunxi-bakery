"""商品后台维护服务。

职责：
- 读取商品规格/属性与生效履约方式；
- 保存商品（标题、价格、库存、上下架、描述、标签）；
- 把后台提交的规格表/属性组转换成有赞同构的 skus_json / item_props_json；
- 新建自有商品（有赞停用后仍可继续上新）；
- 上传商品图到服务器本地目录。

价格与库存口径：
- 有规格时，列表价取最低规格价，库存取各规格之和，避免列表与详情打架；
- 履约方式可覆盖自动推导，解决无规格固定尺寸蛋糕被误判成现货的问题。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.config import settings
from app.logger import setup_logger
from app.repository.knowledge_product_repo import KnowledgeProductRepo
from app.repository.youzan_repo import YouzanProductRepo
from app.service.catalog.product_options import build_product_options
from app.service.order.fulfillment_types import (
    FULFILLMENT_PREORDER_CAKE,
    classify_fulfillment_type,
)

MODE_AUTO = "auto"
MODE_PREORDER = "preorder"
MODE_DIRECT = "direct"
ALLOWED_MODES = {MODE_AUTO: "", MODE_PREORDER: MODE_PREORDER, MODE_DIRECT: MODE_DIRECT}
DEFAULT_VARIANT_PROPERTY = "尺寸"
IMAGE_DIR_NAME = "product-images"
MAX_IMAGE_BYTES = 5 * 1024 * 1024

logger = setup_logger()


def _is_preorder_title(title: str) -> bool:
    """标题命中定制关键词时按预订处理，与前台商品页和下单判定保持一致。"""
    return (
        classify_fulfillment_type({"title": title}, title) == FULFILLMENT_PREORDER_CAKE
    )


class ProductAdminService:
    """商品后台维护服务。"""

    def __init__(
        self,
        product_repo: YouzanProductRepo,
        knowledge_repo: KnowledgeProductRepo | None = None,
    ) -> None:
        self._product_repo = product_repo
        self._knowledge_repo = knowledge_repo

    async def get_product(self, item_id: str) -> dict | None:
        """返回商品原始规格数据与当前生效的履约方式。"""
        normalized = self._normalize_item_id(item_id)
        row = await self._product_repo.get_by_id(normalized)
        if row is None:
            return None
        options = build_product_options(
            str(row.get("skus_json") or ""),
            str(row.get("item_props_json") or ""),
            base_price_fen=int(row.get("price_fen") or 0),
        )
        override = str(row.get("fulfillment_mode") or "").strip()
        title = str(row.get("title") or "")
        effective_mode = override or options["orderMode"]
        if not override and effective_mode == "direct" and _is_preorder_title(title):
            effective_mode = "preorder"
        return {
            "itemId": str(row.get("item_id")),
            "title": title,
            "priceFen": int(row.get("price_fen") or 0),
            "stock": int(row.get("stock") or 0),
            "isActive": int(row.get("is_active") or 0) == 1,
            "image": str(row.get("image") or ""),
            "imageLocal": str(row.get("image_local") or ""),
            "desc": str(row.get("desc") or ""),
            "tags": str(row.get("tags") or ""),
            "fulfillmentMode": override or MODE_AUTO,
            "effectiveOrderMode": effective_mode,
            "variants": options["variants"],
            "options": options["options"],
        }

    async def set_fulfillment_mode(self, item_id: str, mode: str) -> dict:
        """按商品覆盖履约方式；auto 表示回到按有赞数据自动推导。"""
        normalized = self._normalize_item_id(item_id)
        value = str(mode or "").strip().lower()
        if value not in ALLOWED_MODES:
            raise ValueError("履约方式只能是 auto/preorder/direct")
        updated = await self._product_repo.update_fulfillment_mode(
            normalized, ALLOWED_MODES[value]
        )
        if not updated:
            raise ValueError("商品不存在")
        return {"itemId": str(normalized), "fulfillmentMode": value}

    async def save_product(self, item_id: str, payload: dict[str, Any]) -> dict:
        """保存商品编辑结果，并同步知识条目（标题/描述/上下架）。"""
        normalized = self._normalize_item_id(item_id)
        row = await self._product_repo.get_by_id(normalized)
        if row is None:
            raise ValueError("商品不存在")
        fields = self._build_update_fields(payload, normalized, row)
        if not fields:
            raise ValueError("没有需要保存的字段")
        if not await self._product_repo.update_admin_fields(normalized, fields):
            raise ValueError("商品不存在")
        await self._sync_knowledge(normalized, fields, row)
        product = await self.get_product(item_id)
        if product is None:
            raise ValueError("商品不存在")
        return product

    async def create_product(self, payload: dict[str, Any]) -> dict:
        """新建自有商品：编号沿用整数 item_id，方便历史订单继续可查。"""
        item_id = await self._product_repo.next_item_id()
        fields = self._build_update_fields(payload, item_id, {})
        title = str(fields.get("title") or "").strip()
        if not title:
            raise ValueError("商品标题不能为空")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self._product_repo.upsert_product(
            item_id=item_id,
            title=title,
            alias=f"local-{item_id}",
            price_fen=int(fields.get("price_fen") or 0),
            stock=int(fields.get("stock") or 0),
            image=str(fields.get("image") or ""),
            is_active=int(fields.get("is_active", 1)),
            updated_at=now,
            skus_json=str(fields.get("skus_json") or "[]"),
            item_props_json=str(fields.get("item_props_json") or "[]"),
            desc=str(fields.get("desc") or ""),
            tags=str(fields.get("tags") or ""),
            sync_source="admin",
            sync_ref=str(item_id),
        )
        await self._product_repo.update_admin_fields(
            item_id,
            {
                "fulfillment_mode": ALLOWED_MODES[
                    str(fields.get("fulfillment_mode") or MODE_AUTO)
                ]
            },
        )
        if self._knowledge_repo is not None:
            await self._knowledge_repo.upsert_product_knowledge(
                youzan_item_id=str(item_id),
                title=title,
                content=str(fields.get("desc") or title),
                keywords=str(fields.get("tags") or ""),
                priority=10,
                updated_at=now,
                sync_source="admin",
                sync_ref=str(item_id),
            )
        product = await self.get_product(str(item_id))
        if product is None:
            raise ValueError("商品创建失败")
        return product

    async def save_image(self, item_id: str, content: bytes, content_type: str) -> dict:
        """保存后台上传的商品图，并写入本地图片路径。"""
        normalized = self._normalize_item_id(item_id)
        row = await self._product_repo.get_by_id(normalized)
        if row is None:
            raise ValueError("商品不存在")
        if not content:
            raise ValueError("图片内容为空")
        if len(content) > MAX_IMAGE_BYTES:
            raise ValueError("图片不能超过 5MB")
        normalized_type = (content_type or "").split(";")[0].strip().lower()
        extensions = {
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }
        extension = extensions.get(normalized_type)
        if extension is None:
            raise ValueError("只支持 JPG/PNG/WebP 图片")
        image_dir = Path(settings.DB_PATH).resolve().parent / IMAGE_DIR_NAME
        image_dir.mkdir(parents=True, exist_ok=True)
        target = image_dir / f"{normalized}{extension}"
        target.write_bytes(content)
        relative = f"{IMAGE_DIR_NAME}/{target.name}"
        await self._product_repo.update_admin_fields(
            normalized, {"image_local": relative}
        )
        return {"itemId": str(normalized), "imageLocal": relative}

    def _build_update_fields(
        self, payload: dict[str, Any], item_id: int, row: dict
    ) -> dict[str, Any]:
        """校验并转换后台提交的字段；未提交的字段不覆盖。"""
        fields: dict[str, Any] = {}
        if "title" in payload:
            title = str(payload.get("title") or "").strip()
            if not title:
                raise ValueError("商品标题不能为空")
            fields["title"] = title
        if "stock" in payload:
            fields["stock"] = self._to_non_negative(payload.get("stock"), "库存")
        if "isActive" in payload:
            fields["is_active"] = 1 if payload.get("isActive") else 0
        if "desc" in payload:
            fields["desc"] = str(payload.get("desc") or "")
        if "tags" in payload:
            fields["tags"] = self._normalize_tags(payload.get("tags"))
        if "fulfillmentMode" in payload:
            mode = str(payload.get("fulfillmentMode") or "").strip().lower()
            if mode not in ALLOWED_MODES:
                raise ValueError("履约方式只能是 auto/preorder/direct")
            fields["fulfillment_mode"] = ALLOWED_MODES[mode]
        if "variants" in payload:
            skus = self._build_skus_json(payload.get("variants"), item_id, row)
            fields["skus_json"] = skus
            prices = [
                int(sku.get("price") or 0)
                for sku in json.loads(skus)
                if isinstance(sku, dict)
            ]
            if prices:
                fields["price_fen"] = min(prices)
                fields["stock"] = sum(
                    int(sku.get("quantity") or 0)
                    for sku in json.loads(skus)
                    if isinstance(sku, dict)
                )
        if "priceFen" in payload and "price_fen" not in fields:
            fields["price_fen"] = self._to_non_negative(payload.get("priceFen"), "价格")
        if "options" in payload:
            fields["item_props_json"] = self._build_options_json(
                payload.get("options"), row
            )
        return fields

    @staticmethod
    def _build_skus_json(variants: object, item_id: int, row: dict) -> str:
        """把后台规格表转换成有赞同构 SKU：同名规格沿用原 id，避免购物车失效。"""
        if not isinstance(variants, list):
            raise ValueError("规格必须为数组")
        previous: dict[str, int] = {}
        for sku in _loads_list(str(row.get("skus_json") or "[]")):
            name = _sku_display_name(sku)
            if name:
                previous[name] = int(sku.get("sku_id") or 0)
        skus: list[dict[str, Any]] = []
        for index, variant in enumerate(variants):
            if not isinstance(variant, dict):
                raise ValueError("规格格式不正确")
            name = str(variant.get("name") or "").strip()
            if not name:
                raise ValueError("规格名称不能为空")
            price_fen = _to_non_negative_int(variant.get("priceFen"), "规格价格")
            stock = _to_non_negative_int(variant.get("stock"), "规格库存")
            property_name = str(
                variant.get("property") or DEFAULT_VARIANT_PROPERTY
            ).strip()
            sku_id = previous.get(name) or int(f"{item_id}{index + 1}")
            skus.append(
                {
                    "sku_id": sku_id,
                    "price": price_fen,
                    "quantity": stock,
                    "properties_name_json": json.dumps(
                        [{"k": property_name, "v": name}], ensure_ascii=False
                    ),
                }
            )
        return json.dumps(skus, ensure_ascii=False)

    @staticmethod
    def _build_options_json(options: object, row: dict) -> str:
        """把后台属性组转换成有赞同构属性：同名选项沿用原 id。"""
        if not isinstance(options, list):
            raise ValueError("属性组必须为数组")
        previous: dict[str, int] = {}
        for prop in _loads_list(str(row.get("item_props_json") or "[]")):
            for model in _loads_list(prop.get("text_models")):
                name = str(model.get("prop_text_name") or "").strip()
                if name:
                    previous[name] = int(model.get("prop_text_id") or 0)
        props: list[dict[str, Any]] = []
        for index, group in enumerate(options):
            if not isinstance(group, dict):
                raise ValueError("属性组格式不正确")
            name = str(group.get("name") or "").strip()
            if not name:
                raise ValueError("属性组名称不能为空")
            choices: list[dict[str, Any]] = []
            for choice_index, choice in enumerate(group.get("choices") or []):
                if not isinstance(choice, dict):
                    raise ValueError("属性选项格式不正确")
                choice_name = str(choice.get("name") or "").strip()
                if not choice_name:
                    raise ValueError("属性选项名称不能为空")
                choices.append(
                    {
                        "prop_text_id": previous.get(choice_name)
                        or int(f"{index + 1}{choice_index + 1}"),
                        "prop_text_name": choice_name,
                        "price": _to_non_negative_int(
                            choice.get("priceDeltaFen"), "选项加价"
                        ),
                    }
                )
            if not choices:
                raise ValueError(f"属性组「{name}」至少需要一个选项")
            props.append(
                {
                    "prop_name": name,
                    "is_necessary": bool(group.get("required")),
                    "is_multiple": bool(group.get("multiple")),
                    "text_models": choices,
                }
            )
        return json.dumps(props, ensure_ascii=False)

    async def _sync_knowledge(self, item_id: int, fields: dict, row: dict) -> None:
        """商品标题/描述/上下架在知识表里也有一份，编辑后必须同步。"""
        if self._knowledge_repo is None:
            return
        title = str(fields.get("title") or row.get("title") or "")
        content = str(fields.get("desc") or row.get("desc") or title)
        is_active = bool(int(fields.get("is_active", row.get("is_active", 1) or 0)))
        await self._knowledge_repo.update_product_knowledge_admin(
            str(item_id), title=title, content=content, is_active=is_active
        )

    @staticmethod
    def _normalize_tags(value: object) -> str:
        if isinstance(value, list):
            return ", ".join(str(item).strip() for item in value if str(item).strip())
        return str(value or "")

    @staticmethod
    def _to_non_negative(value: object, label: str) -> int:
        return _to_non_negative_int(value, label)

    @staticmethod
    def _normalize_item_id(item_id: str) -> int:
        normalized = str(item_id or "").strip()
        if not normalized.isdigit():
            raise ValueError("商品 ID 无效")
        return int(normalized)


def _to_non_negative_int(value: object, label: str) -> int:
    try:
        number = int(value or 0)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label}必须是整数") from exc
    if number < 0:
        raise ValueError(f"{label}不能为负数")
    return number


def _loads_list(raw: str) -> list[Any]:
    try:
        value = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
    return value if isinstance(value, list) else []


def _sku_display_name(sku: dict) -> str:
    for prop in _loads_list(str(sku.get("properties_name_json") or "[]")):
        if isinstance(prop, dict):
            value = str(prop.get("v") or "").strip()
            if value:
                return value
    return ""


__all__ = ["ProductAdminService"]
