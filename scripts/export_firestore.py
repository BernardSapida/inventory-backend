"""
Read-only Firestore backup for the smartstock-6fb23 project.

Exports EVERY top-level collection (and nested subcollections, recursively)
to timestamped JSON files. Use this BEFORE applying any new schema/migration
so the original data is preserved as an integrity reference.

It does NOT write to or modify Firestore in any way.

Credentials (either one):
  - Place a service account key at  inventory-backend/serviceAccountKey.json
  - or set FIREBASE_SERVICE_ACCOUNT (full JSON string)
  - or set FIREBASE_CREDENTIALS=/path/to/key.json

Run (from inventory-backend/):
  venv/Scripts/python.exe scripts/export_firestore.py        # Windows
  ./venv/bin/python scripts/export_firestore.py              # macOS/Linux

Output:
  inventory-backend/backups/firestore-<UTC-timestamp>/
    <collection>.json          one file per top-level collection
    _manifest.json             collection -> document count, total, generatedAt
"""

import datetime as _dt
import json
import os
import sys

# Make the backend package importable when run from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_db  # noqa: E402


def serialize(value):
    """Convert Firestore/Python types into JSON-friendly values."""
    # Firestore Timestamp / Python datetime
    if isinstance(value, _dt.datetime):
        return {"__type__": "timestamp", "value": value.isoformat()}
    if isinstance(value, (bytes, bytearray)):
        return {"__type__": "bytes", "value": value.hex()}
    if isinstance(value, dict):
        return {k: serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize(v) for v in value]
    # DocumentReference -> path string
    if hasattr(value, "path") and value.__class__.__name__ == "DocumentReference":
        return {"__type__": "ref", "value": value.path}
    # GeoPoint
    if value.__class__.__name__ == "GeoPoint":
        return {"__type__": "geopoint", "lat": value.latitude, "lng": value.longitude}
    return value


def export_doc(doc):
    """Export a single document with its data and any nested subcollections."""
    data = {k: serialize(v) for k, v in (doc.to_dict() or {}).items()}
    out = {"id": doc.id, "data": data}

    subcols = list(doc.reference.collections())
    if subcols:
        out["subcollections"] = {
            sub.id: [export_doc(d) for d in sub.stream()] for sub in subcols
        }
    return out


def main():
    db = get_db()

    stamp = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d-%H%M%SZ")
    out_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "backups",
        f"firestore-{stamp}",
    )
    os.makedirs(out_dir, exist_ok=True)

    manifest = {"generatedAt": stamp, "project": "smartstock-6fb23", "collections": {}}
    total = 0

    collections = list(db.collections())
    if not collections:
        print("No top-level collections found (check credentials / project).")

    for col in collections:
        docs = [export_doc(d) for d in col.stream()]
        with open(os.path.join(out_dir, f"{col.id}.json"), "w", encoding="utf-8") as f:
            json.dump(docs, f, indent=2, ensure_ascii=False)
        manifest["collections"][col.id] = len(docs)
        total += len(docs)
        print(f"  {col.id}: {len(docs)} docs")

    manifest["totalTopLevelDocs"] = total
    with open(os.path.join(out_dir, "_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\nBackup complete -> {out_dir}")
    print(f"Top-level collections: {len(collections)} | total docs: {total}")


if __name__ == "__main__":
    main()
