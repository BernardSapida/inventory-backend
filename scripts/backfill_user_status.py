"""
One-time backfill for the new `status` field on `users/{uid}` docs, added for
the admin-approval signup workflow (web + native now gate login on
status == 'active' instead of only `isActive`).

Every user that existed BEFORE this feature shipped was already vetted (either
seeded, migrated, or manually created) - they should keep working exactly as
before, so they all get `status: 'active'` regardless of their `isActive`
value (isActive stays the separate post-approval on/off toggle).

Only docs with no `status` field are touched, so this is idempotent and safe
to re-run - new signups created after deploy (which set status: 'pending'
themselves) are never touched.

Usage (from inventory-backend/):
  venv/Scripts/python.exe scripts/backfill_user_status.py            # DRY RUN
  venv/Scripts/python.exe scripts/backfill_user_status.py --commit   # apply
"""

import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from db.connection import get_db  # noqa: E402


def main():
    commit = "--commit" in sys.argv
    db = get_db()

    docs = list(db.collection("users").stream())
    missing = [d for d in docs if "status" not in d.to_dict()]

    print(f"users total: {len(docs)}")
    print(f"missing `status`: {len(missing)}")

    if not missing:
        print("Nothing to do.")
        return

    for d in missing:
        data = d.to_dict()
        print(f"  {d.id}  email={data.get('email')!r}  isActive={data.get('isActive')}  -> status='active'")

    if not commit:
        print("\nDry run only - pass --commit to apply.")
        return

    batch = db.batch()
    for d in missing:
        batch.update(d.reference, {"status": "active"})
    batch.commit()
    print(f"\nUpdated {len(missing)} user doc(s).")


if __name__ == "__main__":
    main()
