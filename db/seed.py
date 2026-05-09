from db.connection import get_db

SHELF_LIFE_REFERENCE = [
    {"name": "egg",    "shelf_life_days": 21, "unit": "pcs", "category": "Dairy"},
    {"name": "lemon",  "shelf_life_days": 21, "unit": "pcs", "category": "Fruits"},
    {"name": "onion",  "shelf_life_days": 60, "unit": "pcs", "category": "Vegetables"},
    {"name": "carrot", "shelf_life_days": 28, "unit": "pcs", "category": "Vegetables"},
]

def seed():
    db = get_db()
    col = db.collection("shelf_life_reference")
    for item in SHELF_LIFE_REFERENCE:
        col.document(item["name"]).set(item)
        print(f"Seeded: {item['name']}")
    print("Done.")

if __name__ == "__main__":
    seed()
