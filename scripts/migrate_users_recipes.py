"""
Consolidate legacy duplicate collections into the canonical ones:
    users_web (5) + staff (2)  -->  users
    recipe_web (7) + recipe (1) -->  recipes

NON-DESTRUCTIVE & IDEMPOTENT:
  - Originals are NOT modified or deleted.
  - Dedupe: users by email, recipes by normalized name (skip if already present).
  - Deterministic ids (migrated_<src>_<origId>) so re-running overwrites, not dupes.
  - Migrated docs are tagged `migratedFrom` for traceability.

Legacy users have NO Firebase Auth account (their ids aren't auth uids), so they
are added as `noAuthAccount: true` - visible in user management but cannot log in
until an auth account is created for them.

Usage (from inventory-backend/):
  venv/Scripts/python.exe scripts/migrate_users_recipes.py            # DRY RUN
  venv/Scripts/python.exe scripts/migrate_users_recipes.py --commit   # apply
"""

import sys

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from firebase_admin import firestore  # noqa: E402

from db.connection import get_db  # noqa: E402

STAFF_PERMS = {
    "inventoryView": True,
    "inventoryAdjust": True,
    "recipePrepare": True,
    "inspectionSubmit": True,
    "notificationsView": True,
    "forecastView": False,
    "staffManage": False,
}


def norm_role(role):
    return "admin" if "admin" in str(role or "").strip().lower() else "staff"


def num(v):
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str) and v.strip():
        try:
            return float(v) if "." in v else int(v)
        except ValueError:
            return 0
    return 0


def norm_ingredient(raw):
    # recipe_web ingredients are plain strings (name only); recipes uses dicts.
    if isinstance(raw, str):
        return {"name": raw.strip(), "quantity": 0, "unit": "pcs", "productId": None}
    return {
        "name": raw.get("name") or raw.get("itemName") or "",
        "quantity": num(raw.get("quantity")),
        "unit": raw.get("unit") or "pcs",
        "productId": None,
    }


def main():
    commit = "--commit" in sys.argv
    db = get_db()

    # ---- USERS ----
    existing_user_emails = set()
    for d in db.collection("users").stream():
        e = (d.to_dict() or {}).get("email")
        if e:
            existing_user_emails.add(e.strip().lower())

    user_writes = []  # (docId, data)
    seen_emails = set(existing_user_emails)
    for src in ("users_web", "staff"):
        for doc in db.collection(src).stream():
            data = doc.to_dict() or {}
            email = (data.get("email") or "").strip()
            if not email or email.lower() in seen_emails:
                continue
            seen_emails.add(email.lower())
            user_writes.append(
                (
                    f"migrated_{src}_{doc.id}",
                    {
                        "uid": f"migrated_{src}_{doc.id}",
                        "email": email,
                        "fullName": data.get("name") or data.get("fullName") or "",
                        "role": norm_role(data.get("role")),
                        "isActive": (data.get("status", "Active") == "Active"),
                        "isArchived": False,
                        "shiftOn": False,
                        "phoneNumber": data.get("phone") or data.get("phoneNumber") or "",
                        "unitPreference": "Metric (g/ml)",
                        "permissions": dict(STAFF_PERMS),
                        "photoUrl": "",
                        "createdAt": data.get("createdAt"),
                        "migratedFrom": src,
                        "noAuthAccount": True,
                    },
                )
            )

    # ---- RECIPES ----
    existing_recipe_names = set()
    for d in db.collection("recipes").stream():
        n = (d.to_dict() or {}).get("name")
        if n:
            existing_recipe_names.add(n.strip().lower())

    recipe_writes = []
    seen_names = set(existing_recipe_names)
    for src in ("recipe_web", "recipe"):
        for doc in db.collection(src).stream():
            data = doc.to_dict() or {}
            name = (data.get("name") or "").strip()
            if not name or name.lower() in seen_names:
                continue
            seen_names.add(name.lower())
            ings = data.get("ingredients") or []
            recipe_writes.append(
                (
                    f"migrated_{src}_{doc.id}",
                    {
                        "name": name,
                        "category": data.get("category") or "Main Course",
                        "instructions": data.get("instructions") or "",
                        "servingSize": num(data.get("servingSize") or data.get("servings") or 1) or 1,
                        "ingredients": [norm_ingredient(i) for i in ings if i],
                        "createdBy": "migration",
                        "createdAt": data.get("createdAt"),
                        "updatedAt": firestore.SERVER_TIMESTAMP,
                        "migratedFrom": src,
                    },
                )
            )

    print(f"USERS  -> add {len(user_writes)} (skipped existing/dup by email):")
    for _id, u in user_writes:
        print(f"    + {u['fullName'] or '(no name)'} <{u['email']}> role={u['role']} from {u['migratedFrom']}")
    print(f"RECIPES -> add {len(recipe_writes)} (skipped dup by name):")
    for _id, r in recipe_writes:
        print(f"    + {r['name']} ({r['category']}, {len(r['ingredients'])} ing) from {r['migratedFrom']}")

    if not commit:
        print("\nDRY RUN - no writes. Re-run with --commit to apply.")
        return

    batch = db.batch()
    n = 0
    for col, writes in (("users", user_writes), ("recipes", recipe_writes)):
        for doc_id, data in writes:
            batch.set(db.collection(col).document(doc_id), data, merge=True)
            n += 1
            if n % 400 == 0:
                batch.commit()
                batch = db.batch()
    batch.commit()
    print(f"\nCOMMITTED: {len(user_writes)} users + {len(recipe_writes)} recipes. Originals untouched.")


if __name__ == "__main__":
    main()
