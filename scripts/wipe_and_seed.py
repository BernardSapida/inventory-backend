"""
Wipe all Firebase Auth users and Firestore collections, then re-seed.

Everything the two apps write is cleared, not just what the seeder writes -
otherwise stale used_stock / events / notifications keep pointing at products
that no longer exist. `shelf_life_reference` is reference data (db/seed.py) and
is deliberately left alone.

Usage (from inventory-backend/):
  venv/Scripts/python.exe scripts/wipe_and_seed.py --commit
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from firebase_admin import auth as fb_auth  # noqa: E402

from db.connection import get_db  # noqa: E402

COMMIT = "--commit" in sys.argv

# Real accounts that survive a reset: their Auth login and their `users` profile
# are both left untouched. Everything else - including the previous seeded
# admin/staff pair, which the seeder recreates - is deleted.
KEEP_EMAILS = {
    "daisycanilang@gmail.com",
    "lara@gmail.com",
}

COLLECTIONS = [
    "users",
    "products",
    "inventory_batches",
    "recipes",
    "preparations",
    "used_stock",
    "inventory_events",
    "notifications",
    "inspections",
    "audit_logs",
]


def delete_collection(db, name, keep_uids=frozenset()):
    """Delete every document in `name`. In `users`, documents belonging to a
    KEEP_EMAILS account are skipped so those logins keep their profile."""
    docs = list(db.collection(name).stream())
    kept = 0
    deleted = 0

    for doc in docs:
        if name == "users":
            data = doc.to_dict() or {}
            if doc.id in keep_uids or (data.get("email") or "").lower() in KEEP_EMAILS:
                print(f"  KEPT  users/{doc.id}  ({data.get('email')})")
                kept += 1
                continue
        if COMMIT:
            doc.reference.delete()
        deleted += 1

    verb = "Deleted" if COMMIT else "DRY RUN - would delete"
    suffix = f", kept {kept}" if kept else ""
    print(f"  {len(docs)} documents in '{name}' -> {verb} {deleted}{suffix}.")


def delete_all_auth_users():
    """Delete every Firebase Auth user except the KEEP_EMAILS accounts.
    Returns the uids that were kept, so their `users` profile survives too."""
    page = fb_auth.list_users()
    users = []
    while page:
        for user in page.users:
            users.append((user.uid, (user.email or "").lower()))
        page = page.get_next_page()

    print(f"  {len(users)} Firebase Auth users found")
    keep_uids = set()

    for uid, email in users:
        if email in KEEP_EMAILS:
            keep_uids.add(uid)
            print(f"  KEPT     auth user  {email}  (uid={uid})")
            continue
        if COMMIT:
            fb_auth.delete_user(uid)
        print(f"  {'DELETED' if COMMIT else 'DRY'}  auth user  {email or uid}  (uid={uid})")

    return keep_uids


def main():
    db = get_db()

    print("\n=== WIPE: Firebase Auth users ===")
    keep_uids = delete_all_auth_users()

    print("\n=== WIPE: Firestore collections ===")
    for col in COLLECTIONS:
        print(f"\n  [{col}]")
        delete_collection(db, col, keep_uids)

    if not COMMIT:
        print("\n── DRY RUN - no deletes. Re-run with --commit to apply. ──────────")
        return

    print("\n── Wipe complete. Running seeder... ───────────────────────────────\n")

    # Import and run the seeder directly
    import scripts.seed_data as seeder  # noqa: E402
    seeder.main()


if __name__ == "__main__":
    main()
