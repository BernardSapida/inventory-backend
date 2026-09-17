"""
One-time Firestore copy: source project (smartstock-6fb23, the client's
project) -> target project (smartstock-9594b, the new project we're moving
to). This is step 1 of the Firebase project migration - Auth users are
migrated separately (see migrate_auth_users.py).

Walks every top-level collection in the source project (no hardcoded
collection names - whatever exists gets copied) and every document within
it, recursively into subcollections, preserving collection names and
document IDs exactly. IDs must be preserved because `users/{uid}` docs are
keyed by the Firebase Auth uid, and the Auth migration step re-creates those
same uids in the target project - if the doc IDs didn't match, every user's
profile would be orphaned from their login.

NON-DESTRUCTIVE & IDEMPOTENT: writes are `set(..., merge=True)`, so
re-running after fixing an issue - or to pick up late changes on the source
- is safe: it won't create duplicates, and a field that exists on the target
but not in the source snapshot (e.g. `status`, backfilled directly on the
target) is left alone rather than clobbered. It does not delete or modify
anything in the source project.

Usage (from inventory-backend/):
  venv/Scripts/python.exe scripts/migrate_firestore_project.py            # DRY RUN
  venv/Scripts/python.exe scripts/migrate_firestore_project.py --commit   # apply
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import firebase_admin  # noqa: E402
from firebase_admin import credentials, firestore  # noqa: E402

SOURCE_KEY = "serviceAccountKey-old.json"
TARGET_KEY = "serviceAccountKey.json"


def get_client(key_path, app_name):
    cred = credentials.Certificate(key_path)
    app = firebase_admin.initialize_app(cred, name=app_name)
    return firestore.client(app)


def copy_collection(src_coll_ref, dst_coll_ref, commit, path_label, counts):
    for doc in src_coll_ref.stream():
        data = doc.to_dict()
        counts[path_label] = counts.get(path_label, 0) + 1
        print(f"  {path_label}/{doc.id}")
        dst_doc_ref = dst_coll_ref.document(doc.id)
        if commit:
            # merge=True: a field that exists on the target but not in this
            # source snapshot (e.g. `status`, backfilled directly on the
            # target after an earlier sync) survives a re-run instead of
            # being clobbered by a full overwrite.
            dst_doc_ref.set(data, merge=True)

        for sub_coll_ref in doc.reference.collections():
            sub_label = f"{path_label}/{doc.id}/{sub_coll_ref.id}"
            copy_collection(sub_coll_ref, dst_doc_ref.collection(sub_coll_ref.id), commit, sub_label, counts)


def main():
    commit = "--commit" in sys.argv

    for key in (SOURCE_KEY, TARGET_KEY):
        if not os.path.exists(key):
            print(f"Missing {key} in inventory-backend/")
            sys.exit(1)

    src_db = get_client(SOURCE_KEY, "source")
    dst_db = get_client(TARGET_KEY, "target")

    collections = list(src_db.collections())
    print(f"Source collections found: {[c.id for c in collections]}")
    print(f"Mode: {'COMMIT' if commit else 'DRY RUN'}\n")

    counts = {}
    for coll in collections:
        copy_collection(coll, dst_db.collection(coll.id), commit, coll.id, counts)

    print("\nSummary:")
    for label, n in sorted(counts.items()):
        print(f"  {label}: {n} document(s)")
    print(f"\nTotal: {sum(counts.values())} document(s)")

    if not commit:
        print("\nDry run only - pass --commit to actually write to the target project.")


if __name__ == "__main__":
    main()
