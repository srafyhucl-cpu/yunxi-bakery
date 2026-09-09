"""配送报价快照仓储。"""

from app.models.delivery import DeliveryQuote, DeliveryQuoteStatus, FulfillmentMethod
from app.repository.base import BaseRepository


class DeliveryQuoteRepo(BaseRepository):
    """保存和读取小程序配送报价。"""

    async def create(self, quote: DeliveryQuote) -> None:
        await self._db.execute(
            "INSERT INTO delivery_quotes ("
            "quote_id, user_id, fulfillment_method, request_hash, goods_total_fen, "
            "delivery_fee_fen, quote_total_fen, status, provider, message, expires_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                quote.quote_id,
                quote.user_id,
                quote.fulfillment_method.value,
                quote.request_hash,
                quote.goods_total_fen,
                quote.delivery_fee_fen,
                quote.quote_total_fen,
                quote.status.value,
                quote.provider,
                quote.message,
                quote.expires_at,
            ),
        )

    async def get_for_user(self, quote_id: str, user_id: str) -> DeliveryQuote | None:
        rows = await self._db.execute_fetchall(
            "SELECT quote_id, user_id, fulfillment_method, request_hash, "
            "goods_total_fen, delivery_fee_fen, quote_total_fen, status, provider, "
            "message, expires_at FROM delivery_quotes "
            "WHERE quote_id = ? AND user_id = ? LIMIT 1",
            (quote_id, user_id),
        )
        if not rows:
            return None
        row = rows[0]
        return DeliveryQuote(
            quote_id=str(row["quote_id"]),
            user_id=str(row["user_id"]),
            fulfillment_method=FulfillmentMethod(str(row["fulfillment_method"])),
            request_hash=str(row["request_hash"]),
            goods_total_fen=int(row["goods_total_fen"]),
            delivery_fee_fen=(
                int(row["delivery_fee_fen"])
                if row["delivery_fee_fen"] is not None
                else None
            ),
            quote_total_fen=(
                int(row["quote_total_fen"])
                if row["quote_total_fen"] is not None
                else None
            ),
            status=DeliveryQuoteStatus(str(row["status"])),
            provider=str(row["provider"]),
            message=str(row["message"]),
            expires_at=str(row["expires_at"]),
        )

    async def update_status(self, quote_id: str, status: DeliveryQuoteStatus) -> None:
        await self._db.execute(
            "UPDATE delivery_quotes SET status = ? WHERE quote_id = ?",
            (status.value, quote_id),
        )
