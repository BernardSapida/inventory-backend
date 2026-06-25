"""
Backfill preparedByName / preparedByRole on existing preparation documents.

App-created preparations snapshot the actor's name at prep time and never wrote
preparedByRole. After renaming users (e.g. Staff User → John Doe) those old docs
are stale. This script re-reads each preparation's preparedBy uid, looks up the
current users/<uid> profile, and refreshes preparedByName + preparedByRole.

Usage (from inventory-backend/):
  venv/Scripts/python.exe scripts/backfill_preparation_actors.py            # dry run
  venv/Scripts/python.exe scripts/backfill_preparation_actors.py --commit   # apply
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from db.connection import get_db  # noqa: E402

COMMIT = "--commit" in sys.argv


def main():
    db = get_db()

    # Cache user profiles so we don't re-fetch per preparation.
    user_cache: dict[str, dict] = {}

    def lookup(uid: str):
        if uid not in user_cache:
            snap = db.collection("users").document(uid).get()
            user_cache[uid] = snap.to_dict() if snap.exists else None
        return user_cache[uid]

    print("\n=== BACKFILL PREPARATIONS ===")
    updated = skipped = missing = 0

    for doc in db.collection("preparations").stream():
        data = doc.to_dict()
        uid = data.get("preparedBy")
        profile = lookup(uid) if uid else None

        if not profile:
            missing += 1
            print(f"  SKIP  preparations/{doc.id}  (no user for preparedBy={uid!r})")
            continue

        new_name = profile.get("fullName", data.get("preparedByName", ""))
        new_role = profile.get("role", "")

        if data.get("preparedByName") == new_name and data.get("preparedByRole") == new_role:
            skipped += 1
            continue

        old = f"{data.get('preparedByName')!r}/{data.get('preparedByRole')!r}"
        print(f"  {'SET' if COMMIT else 'DRY'}  preparations/{doc.id}  {old} -> {new_name!r}/{new_role!r}")
        if COMMIT:
            doc.reference.update({"preparedByName": new_name, "preparedByRole": new_role})
        updated += 1

    print(f"\n── {'DONE' if COMMIT else 'DRY RUN'}: {updated} to update, "
          f"{skipped} already correct, {missing} with no matching user. ──")
    if not COMMIT:
        print("── Re-run with --commit to apply. ──")


if __name__ == "__main__":
    main()
