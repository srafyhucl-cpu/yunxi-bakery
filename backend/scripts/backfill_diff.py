import sqlite3
import json

db_path = "/opt/apps/yunxibakebot/data/bot.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute(
    "SELECT DISTINCT entity_key FROM content_change_history WHERE entity_type = 'product'"
)
products = cursor.fetchall()
count = 0

for prod in products:
    item_id = prod["entity_key"]
    cursor.execute(
        "SELECT id, change_summary_json FROM content_change_history WHERE entity_type = 'product' AND entity_key = ? ORDER BY id ASC",
        (item_id,),
    )
    history = cursor.fetchall()

    last_price = None
    last_stock = None

    for row in history:
        row_id = row["id"]
        try:
            summary = json.loads(row["change_summary_json"])
        except Exception:
            continue

        modified = False

        if "price_fen" in summary:
            if "old_price_fen" not in summary and last_price is not None:
                if last_price != summary["price_fen"]:
                    summary["old_price_fen"] = last_price
                    modified = True
            last_price = summary["price_fen"]

        if "stock" in summary:
            if "old_stock" not in summary and last_stock is not None:
                if last_stock != summary["stock"]:
                    summary["old_stock"] = last_stock
                    modified = True
            last_stock = summary["stock"]

        if modified:
            cursor.execute(
                "UPDATE content_change_history SET change_summary_json = ? WHERE id = ?",
                (json.dumps(summary, ensure_ascii=False), row_id),
            )
            count += 1

conn.commit()
conn.close()
print(f"Backfill complete, updated {count} records.")
