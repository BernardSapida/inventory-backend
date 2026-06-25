"""
Fix recipes after consolidation:
  1. Relink each ingredient to a `products` doc id (match by name).
  2. Migrate legacy/meal-time categories to the standard culinary set.

NON-DESTRUCTIVE-ish: only updates the `recipes` collection in place (ingredients
get a productId; category remapped). Run dry-run first.

Usage (from inventory-backend/):
  venv/Scripts/python.exe scripts/migrate_recipes_fix.py            # DRY RUN
  venv/Scripts/python.exe scripts/migrate_recipes_fix.py --commit
"""

import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from db.connection import get_db  # noqa: E402

# legacy / meal-time -> standard culinary course
CATEGORY_MAP = {
    "breakfast": "Main Course",
    "lunch": "Main Course",
    "dinner": "Main Course",
    "snack": "Appetizer",
    "general": "Main Course",
    "meal": "Main Course",
    # already-standard pass through:
    "appetizer": "Appetizer",
    "soup": "Soup",
    "salad": "Salad",
    "main course": "Main Course",
    "side dish": "Side Dish",
    "dessert": "Dessert",
    "beverage": "Beverage",
    "sauce/condiment": "Sauce/Condiment",
}


def map_category(cat):
    return CATEGORY_MAP.get(str(cat or "").strip().lower(), "Main Course")


def main():
    commit = "--commit" in sys.argv
    db = get_db()

    # product name (lowercase) -> id
    prod_index = {}
    for d in db.collection("products").stream():
        nm = (d.to_dict() or {}).get("name")
        if nm:
            prod_index[nm.strip().lower()] = d.id

    updates = []
    linked = 0
    unlinked = 0
    for doc in db.collection("recipes").stream():
        data = doc.to_dict() or {}
        ings = data.get("ingredients") or []
        new_ings = []
        for i in ings:
            if not isinstance(i, dict):
                continue
            name = (i.get("name") or i.get("itemName") or "").strip()
            pid = prod_index.get(name.lower())
            if pid:
                linked += 1
            elif name:
                unlinked += 1
            new_ings.append({
                "name": name,
                "quantity": i.get("quantity", 0),
                "unit": i.get("unit", "pcs"),
                "productId": pid,
            })
        new_cat = map_category(data.get("category"))
        updates.append((doc.id, data.get("name", ""), data.get("category"), new_cat, new_ings))

    print(f"Recipes: {len(updates)} | ingredient links: {linked} matched, {unlinked} unlinked")
    for _id, name, old_cat, new_cat, _ings in updates:
        flag = "" if old_cat == new_cat else f"  [{old_cat} -> {new_cat}]"
        print(f"    {name}{flag}")

    if not commit:
        print("\nDRY RUN - no writes. Re-run with --commit to apply.")
        return

    batch = db.batch()
    n = 0
    for doc_id, _name, _old, new_cat, new_ings in updates:
        batch.update(db.collection("recipes").document(doc_id), {"ingredients": new_ings, "category": new_cat})
        n += 1
        if n % 400 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()
    print(f"\nCOMMITTED: updated {len(updates)} recipes ({linked} ingredient links).")


if __name__ == "__main__":
    main()
