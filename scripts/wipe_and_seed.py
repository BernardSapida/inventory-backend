"""
Wipe all Firebase Auth users and Firestore collections, then re-seed.

Collections wiped: users, products, inventory_batches, recipes, preparations

Usage (from inventory-backend/):
  venv/Scripts/python.exe scripts/wipe_and_seed.py --commit
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from firebase_admin import auth as fb_auth  # noqa: E402

from db.connection import get_db  # noqa: E402

COMMIT = "--commit" in sys.argv

COLLECTIONS = ["users", "products", "inventory_batches", "recipes", "preparations"]


def delete_collection(db, name):
    docs = list(db.collection(name).stream())
    print(f"  {len(docs)} documents in '{name}'")
    for doc in docs:
        if COMMIT:
            doc.reference.delete()
    if COMMIT:
        print(f"  -> Deleted all {len(docs)} documents.")
    else:
        print(f"  -> DRY RUN - would delete {len(docs)} documents.")


def delete_all_auth_users():
    page = fb_auth.list_users()
    uids = []
    while page:
        for user in page.users:
            uids.append(user.uid)
        page = page.get_next_page()

    print(f"  {len(uids)} Firebase Auth users found")
    if not uids:
        return

    for uid in uids:
        email = ""
        try:
            email = fb_auth.get_user(uid).email or uid
        except Exception:
            email = uid
        if COMMIT:
            fb_auth.delete_user(uid)
        print(f"  {'DELETED' if COMMIT else 'DRY'}  auth user  {email}  (uid={uid})")


def main():
    db = get_db()

    print("\n=== WIPE: Firebase Auth users ===")
    delete_all_auth_users()

    print("\n=== WIPE: Firestore collections ===")
    for col in COLLECTIONS:
        print(f"\n  [{col}]")
        delete_collection(db, col)

    if not COMMIT:
        print("\n── DRY RUN - no deletes. Re-run with --commit to apply. ──────────")
        return

    print("\n── Wipe complete. Running seeder... ───────────────────────────────\n")

    # Import and run the seeder directly
    import scripts.seed_data as seeder  # noqa: E402
    seeder.main()


if __name__ == "__main__":
    main()
