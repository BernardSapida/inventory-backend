"""
Inventory REST endpoints - repointed to the BATCH MODEL
(`products` + `inventory_batches`), the shared source of truth.

- GET    /inventory          -> products with computed on-hand (sum of batches)
- POST   /inventory          -> for each scanned item: MATCH an existing product
                                (by name, case-insensitive) and ADD a batch using
                                THAT product's unit + shelf life. The scanner never
                                creates products or guesses units - admin owns the
                                product catalog; the scanner only adds stock.
                                Unmatched names are skipped and reported back.
- DELETE /inventory/{id}     -> delete a product and all its batches

Note: the apps mostly use the Firestore client SDK directly; these endpoints
remain for the backend/scanner save path and parity. The batch schema matches
smartstock-admin's addBatch so mobile, scanner and web stay in sync.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Path
from firebase_admin import firestore
from loguru import logger
from pydantic import BaseModel

from db.connection import get_db

router = APIRouter()

# display unit -> (base unit, factor to base, canonical display unit).
# Mirrors smartstock-admin's UNIT_TABLE (src/lib/units.ts) so conversions match.
UNIT_MAP = {
    "mg": ("g", 0.001, "g"),
    "g": ("g", 1, "g"), "gram": ("g", 1, "g"), "grams": ("g", 1, "g"),
    "kg": ("g", 1000, "kg"),
    "ml": ("ml", 1, "ml"),
    "l": ("ml", 1000, "L"), "liter": ("ml", 1000, "L"), "liters": ("ml", 1000, "L"),
    "tbsp": ("ml", 14.787, "tbsp"), "tablespoon": ("ml", 14.787, "tbsp"),
    "tsp": ("ml", 4.929, "tsp"), "teaspoon": ("ml", 4.929, "tsp"),
    "cup": ("ml", 240, "cup"),
    "oz": ("ml", 29.574, "oz"),
    "pcs": ("piece", 1, "pcs"), "piece": ("piece", 1, "pcs"), "pieces": ("piece", 1, "pcs"),
    "bottle": ("piece", 1, "bottles"), "bottles": ("piece", 1, "bottles"),
}
DEFAULT_UNIT = ("piece", 1, "pcs")


def norm_unit(unit):
    return UNIT_MAP.get(str(unit or "").strip().lower(), DEFAULT_UNIT)


def parse_expiry(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO date/datetime string into a tz-aware datetime.

    The Firestore Admin SDK stores Python datetimes as Timestamps, matching
    admin's `Timestamp.fromDate(...)`. Returns None for empty/invalid input.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).strip())
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class InventoryItem(BaseModel):
    name: str
    quantity: float
    unit: Optional[str] = "pcs"
    category: Optional[str] = None
    expirationDate: Optional[str] = None  # ISO date string; user-confirmed


class SaveItemsRequest(BaseModel):
    items: list[InventoryItem]
    addedBy: Optional[str] = None  # actor display name; falls back to "Scanner"


@router.get("/inventory")
def get_inventory():
    db = get_db()
    try:
        products = {d.id: {"id": d.id, **(d.to_dict() or {}), "onHand": 0, "batches": 0} for d in db.collection("products").stream()}
        for b in db.collection("inventory_batches").stream():
            data = b.to_dict() or {}
            pid = data.get("productId")
            if pid in products:
                products[pid]["onHand"] += data.get("quantity", 0) or 0
                products[pid]["batches"] += 1
        return list(products.values())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/inventory")
def save_inventory(request: SaveItemsRequest):
    db = get_db()
    added_by = (request.addedBy or "").strip() or "Scanner"
    try:
        # Admin owns the catalog. Build a name -> product lookup (case-insensitive)
        # so a scanned "egg" matches admin's "Egg". We DO NOT create products here.
        products_by_name: dict[str, dict] = {}
        for d in db.collection("products").stream():
            data = d.to_dict() or {}
            name = (data.get("name") or "").strip().lower()
            if name:
                products_by_name.setdefault(name, {"id": d.id, **data})

        added: list[str] = []
        skipped: list[str] = []

        for item in request.items:
            product = products_by_name.get(item.name.strip().lower())
            if not product:
                # Unknown item - the scanner can't add stock for a product the
                # admin hasn't created. Report it back instead of inventing one.
                skipped.append(item.name)
                logger.warning(f"⚠️ No matching product for '{item.name}' - skipped")
                continue

            # Unit comes from the PRODUCT, not the scan payload.
            _, factor, _ = norm_unit(product.get("displayUnit"))

            # Expiry: prefer the product's shelf life (admin-defined), else the
            # value the scanner computed/confirmed.
            shelf_life = product.get("shelfLifeDays")
            if shelf_life:
                expiry = (datetime.now(timezone.utc) + timedelta(days=int(shelf_life))).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
            else:
                expiry = parse_expiry(item.expirationDate)

            db.collection("inventory_batches").add({
                "productId": product["id"],
                "quantity": item.quantity * factor,
                "expirationDate": expiry,
                "receivedDate": firestore.SERVER_TIMESTAMP,
                "location": None,
                "source": "scan",
                "addedBy": added_by,
            })
            added.append(product.get("name") or item.name)
            logger.info(
                f"📦 Added batch for '{product.get('name')}' "
                f"(+{item.quantity} {product.get('displayUnit')})"
            )

        return {
            "message": f"Added {len(added)} batch(es).",
            "added": added,
            "skipped": skipped,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/inventory/{product_id}")
def delete_product(product_id: str = Path(...)):
    db = get_db()
    try:
        prod_ref = db.collection("products").document(product_id)
        if not prod_ref.get().exists:
            raise HTTPException(status_code=404, detail=f"Product {product_id} not found")
        for b in db.collection("inventory_batches").where("productId", "==", product_id).stream():
            b.reference.delete()
        prod_ref.delete()
        logger.info(f"🗑️ Deleted product + batches id={product_id}")
        return {"message": f"Product {product_id} and its batches deleted"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
