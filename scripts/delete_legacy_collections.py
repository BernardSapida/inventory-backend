"""
Delete legacy collections that have been merged into the canonical ones.
DESTRUCTIVE - but full backups exist in inventory-backend/backups/.

Pass the collection names to delete as args, plus --commit to actually delete:
  venv/Scripts/python.exe scripts/delete_legacy_collections.py users_web staff recipe_web recipe            # DRY RUN
  venv/Scripts/python.exe scripts/delete_legacy_collections.py users_web staff recipe_web recipe --commit   # delete
"""

import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from db.connection import get_db  # noqa: E402

# Safety: never allow deleting the canonical collections.
PROTECTED = {"users", "recipes", "products", "inventory_batches", "audit_logs", "notifications",
             "preparations", "inventory_events", "shelf_life_reference", "system_config", "inspections"}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    commit = "--commit" in sys.argv
    if not args:
        print("Pass collection names to delete.")
        return
    bad = [a for a in args if a in PROTECTED]
    if bad:
        print(f"REFUSING to delete protected collections: {bad}")
        return

    db = get_db()
    for name in args:
        docs = list(db.collection(name).stream())
        print(f"{name}: {len(docs)} docs", "-> DELETE" if commit else "(dry run)")
        if commit:
            batch = db.batch()
            for i, d in enumerate(docs, 1):
                batch.delete(d.reference)
                if i % 400 == 0:
                    batch.commit()
                    batch = db.batch()
            batch.commit()
    print("\nDone." if commit else "\nDRY RUN - add --commit to delete.")


if __name__ == "__main__":
    main()
