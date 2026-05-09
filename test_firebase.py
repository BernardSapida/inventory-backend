from db.connection import get_db
import json

db = get_db()
docs = db.collection("inventory_items").stream()
items = [{"id": doc.id, **doc.to_dict()} for doc in docs]
print(json.dumps(items, indent=2, default=str))
