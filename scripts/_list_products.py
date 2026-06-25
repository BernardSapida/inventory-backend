import sys
sys.path.insert(0, ".")
from db.connection import get_db

db = get_db()
docs = list(db.collection("products").stream())
docs.sort(key=lambda d: (d.to_dict().get("category", ""), d.to_dict().get("name", "")))
print(f"Total: {len(docs)} products\n")
for doc in docs:
    d = doc.to_dict()
    print(f"  [{d.get('category','?')}]  {d.get('name','?')}  ({d.get('displayUnit','?')})  id={doc.id}")
