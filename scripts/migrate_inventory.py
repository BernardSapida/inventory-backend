"""
Consolidate the THREE legacy inventory collections into the new batch model:
    inventory, inventory_items, inventory_items_web
        -->  products  (catalog: what an item IS)
        +    inventory_batches  (on-hand stock, each with its own expiry)

NON-DESTRUCTIVE & IDEMPOTENT:
  - Original collections are NOT modified or deleted.
  - Deterministic doc ids (product = slug(name|baseUnit), batch = <source>__<docId>)
    so re-running overwrites the same docs instead of duplicating.
  - To undo: delete the `products` and `inventory_batches` collections.

Usage (from inventory-backend/):
  venv/Scripts/python.exe scripts/migrate_inventory.py            # DRY RUN (no writes)
  venv/Scripts/python.exe scripts/migrate_inventory.py --commit   # write to Firestore
"""

import datetime as _dt
import re
import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from db.connection import get_db  # noqa: E402

SOURCES = ["inventory", "inventory_items", "inventory_items_web"]

# unit -> (base unit, factor to base, canonical display unit)
UNIT_MAP = {
    "kg": ("g", 1000, "kg"),
    "g": ("g", 1, "g"),
    "gram": ("g", 1, "g"),
    "grams": ("g", 1, "g"),
    "mg": ("g", 0.001, "g"),
    "l": ("ml", 1000, "L"),
    "liter": ("ml", 1000, "L"),
    "liters": ("ml", 1000, "L"),
    "ml": ("ml", 1, "ml"),
    "pcs": ("piece", 1, "pcs"),
    "piece": ("piece", 1, "pcs"),
    "pieces": ("piece", 1, "pcs"),
    "bottle": ("piece", 1, "bottles"),
    "bottles": ("piece", 1, "bottles"),
}
DEFAULT_UNIT = ("piece", 1, "pcs")  # for web items that have no unit


def norm_unit(unit):
    if not unit:
        return DEFAULT_UNIT
    return UNIT_MAP.get(str(unit).strip().lower(), DEFAULT_UNIT)


def slug(s):
    return re.sub(r"[^a-z0-9]+", "-", str(s).strip().lower()).strip("-")


def parse_expiry(data):
    # inventory / inventory_items: expirationDate (Timestamp). web: expiryDate (string "YYYY-MM-DD").
    if data.get("expirationDate"):
        return data["expirationDate"]
    raw = data.get("expiryDate")
    if isinstance(raw, str) and raw.strip():
        try:
            return _dt.datetime.fromisoformat(raw.strip())
        except ValueError:
            return None
    return raw or None


def main():
    commit = "--commit" in sys.argv
    db = get_db()

    # shelf-life lookup by lowercase name
    shelf = {}
    for d in db.collection("shelf_life_reference").stream():
        sd = d.to_dict() or {}
        nm = str(sd.get("name", d.id)).strip().lower()
        if sd.get("shelf_life_days") is not None:
            shelf[nm] = sd["shelf_life_days"]

    products = {}  # productId -> product dict
    batches = []  # list of (batchId, batch dict)

    for col in SOURCES:
        for doc in db.collection(col).stream():
            data = doc.to_dict() or {}
            name = (data.get("name") or "").strip()
            if not name:
                continue
            base_unit, factor, display_unit = norm_unit(data.get("unit"))
            pid = slug(f"{name}__{base_unit}")

            # --- product (merge by name+baseUnit; first richer source wins) ---
            min_threshold = data.get("minimumThreshold")
            if min_threshold is None:
                min_threshold = data.get("reorderLevel")
            min_threshold_base = (min_threshold * factor) if isinstance(min_threshold, (int, float)) else None

            if pid not in products:
                products[pid] = {
                    "name": name,
                    "category": (data.get("category") or "Uncategorized").strip(),
                    "baseUnit": base_unit,
                    "displayUnit": display_unit,
                    "minimumThreshold": min_threshold_base,
                    "shelfLifeDays": shelf.get(name.lower()),
                    "barcode": data.get("barcode") or "",
                    "countable": data.get("countable", base_unit == "piece"),
                    "sourceCollections": [col],
                }
            else:
                p = products[pid]
                if p.get("minimumThreshold") is None and min_threshold_base is not None:
                    p["minimumThreshold"] = min_threshold_base
                if not p.get("barcode") and data.get("barcode"):
                    p["barcode"] = data["barcode"]
                if col not in p["sourceCollections"]:
                    p["sourceCollections"].append(col)

            # --- batch (one per source doc) ---
            qty = data.get("quantity")
            if isinstance(qty, (int, float)):
                batches.append(
                    (
                        f"{col}__{doc.id}",
                        {
                            "productId": pid,
                            "quantity": qty * factor,  # stored in base unit
                            "expirationDate": parse_expiry(data),
                            "receivedDate": data.get("createdAt") or data.get("updatedAt"),
                            "location": data.get("location"),
                            "source": "migration",
                            "addedBy": data.get("updatedBy") or "migration",
                            "sourceCollection": col,
                            "sourceDocId": doc.id,
                        },
                    )
                )

    print(f"Planned: {len(products)} products, {len(batches)} batches (from {', '.join(SOURCES)})")
    multi = {pid: p for pid, p in products.items() if len(p["sourceCollections"]) > 1}
    if multi:
        print(f"  {len(multi)} products merged across multiple source collections:")
        for pid, p in list(multi.items())[:15]:
            print(f"    - {p['name']} ({p['baseUnit']}) <- {', '.join(p['sourceCollections'])}")

    if not commit:
        print("\nDRY RUN - no writes. Re-run with --commit to apply.")
        return

    batch = db.batch()
    n = 0
    for pid, p in products.items():
        batch.set(db.collection("products").document(pid), p, merge=True)
        n += 1
        if n % 400 == 0:
            batch.commit()
            batch = db.batch()
    for bid, b in batches:
        batch.set(db.collection("inventory_batches").document(bid), b, merge=True)
        n += 1
        if n % 400 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()

    print(f"\nCOMMITTED: {len(products)} products + {len(batches)} batches written.")
    print("Originals untouched. To undo: delete `products` and `inventory_batches`.")


if __name__ == "__main__":
    main()
