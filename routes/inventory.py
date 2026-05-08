from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel
from typing import List, Optional
from datetime import date, datetime
from db.connection import get_connection
from loguru import logger

router = APIRouter()


class InventoryItem(BaseModel):
    name: str
    quantity: int
    shelf_life_days: Optional[int] = None
    date_received: Optional[date] = None
    expiry_date: Optional[date] = None


class SaveItemsRequest(BaseModel):
    items: List[InventoryItem]


@router.get("/inventory")
def get_inventory():
    conn = get_connection()
    cur = conn.cursor()
    try:
        logger.info("📋 Fetching all inventory items...")
        cur.execute(
            """
            SELECT id, name, quantity, shelf_life_days, date_received, expiry_date, created_at
            FROM inventory_items
            ORDER BY created_at DESC
            """
        )
        rows = cur.fetchall()
        return [
            {
                "id": row[0],
                "name": row[1],
                "quantity": row[2],
                "shelf_life_days": row[3],
                "date_received": row[4],
                "expiry_date": row[5],
                "created_at": row[6],
            }
            for row in rows
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        logger.success("✅ Inventory fetched successfully!")
        cur.close()
        conn.close()


@router.post("/inventory")
def save_inventory(request: SaveItemsRequest):
    conn = get_connection()
    cur = conn.cursor()
    try:
        for item in request.items:
            cur.execute(
                "SELECT id FROM inventory_items WHERE name = %s ORDER BY created_at DESC LIMIT 1",
                (item.name,),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    "UPDATE inventory_items SET quantity = quantity + %s WHERE id = %s",
                    (item.quantity, existing[0]),
                )
                logger.info(f"📦 Updated quantity for '{item.name}' (+{item.quantity})")
            else:
                cur.execute(
                    """
                    INSERT INTO inventory_items (name, quantity, shelf_life_days, date_received, expiry_date)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        item.name,
                        item.quantity,
                        item.shelf_life_days,
                        item.date_received or date.today(),
                        item.expiry_date,
                    ),
                )
                logger.info(f"📦 Inserted new item '{item.name}' (qty: {item.quantity})")
        conn.commit()
        return {"message": "Items saved successfully"}
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()


@router.delete("/inventory/{item_id}")
def delete_inventory_item(item_id: int = Path(..., gt=0)):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM inventory_items WHERE id = %s", (item_id,))
        if cur.fetchone() is None:
            raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
        cur.execute("DELETE FROM inventory_items WHERE id = %s", (item_id,))
        conn.commit()
        logger.info(f"🗑️ Deleted inventory item id={item_id}")
        return {"message": f"Item {item_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close()
        conn.close()
