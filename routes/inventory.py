from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
from google.cloud.firestore_v1 import DELETE_FIELD
from db.connection import get_db
from loguru import logger

router = APIRouter()


class InventoryItem(BaseModel):
    name: str
    quantity: int
    unit: Optional[str] = "pcs"
    category: Optional[str] = None
    expirationDate: Optional[str] = None


class SaveItemsRequest(BaseModel):
    items: list[InventoryItem]


@router.get("/inventory")
def get_inventory():
    db = get_db()
    try:
        logger.info("📋 Fetching all inventory items...")
        docs = db.collection("inventory").order_by("createdAt").stream()
        items = [{"id": doc.id, **doc.to_dict()} for doc in docs]
        logger.success("✅ Inventory fetched successfully!")
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inventory")
def save_inventory(request: SaveItemsRequest):
    db = get_db()
    col = db.collection("inventory")
    now = datetime.now(timezone.utc)
    try:
        for item in request.items:
            existing = col.where("name", "==", item.name).limit(1).stream()
            docs = list(existing)
            if docs:
                doc_ref = col.document(docs[0].id)
                doc_ref.update({
                    "quantity": docs[0].to_dict()["quantity"] + item.quantity,
                    "updatedAt": now,
                })
                logger.info(f"📦 Updated quantity for '{item.name}' (+{item.quantity})")
            else:
                col.add({
                    "name": item.name,
                    "quantity": item.quantity,
                    "unit": item.unit,
                    "category": item.category,
                    "expirationDate": item.expirationDate,
                    "status": "ok",
                    "countable": True,
                    "barcode": "",
                    "minimumThreshold": 0,
                    "updatedBy": "scanner",
                    "createdAt": now,
                    "updatedAt": now,
                })
                logger.info(f"📦 Inserted new item '{item.name}' (qty: {item.quantity})")
        return {"message": "Items saved successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/inventory/{item_id}")
def delete_inventory_item(item_id: str = Path(...)):
    db = get_db()
    col = db.collection("inventory")
    try:
        doc_ref = col.document(item_id)
        if not doc_ref.get().exists:
            raise HTTPException(status_code=404, detail=f"Item {item_id} not found")
        doc_ref.delete()
        logger.info(f"🗑️ Deleted inventory item id={item_id}")
        return {"message": f"Item {item_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
