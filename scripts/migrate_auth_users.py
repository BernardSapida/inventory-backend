"""
One-time Auth user migration: source project (smartstock-6fb23) -> target
project (smartstock-9594b). This is step 2 of the Firebase project migration
(step 1 was Firestore, see migrate_firestore_project.py).

We do NOT attempt to preserve exact password hashes - that needs the source
project's scrypt hash-key, which requires IAM permissions we don't have on
the client's GCP project (confirmed: USER_PROJECT_DENIED on the Identity
Toolkit config API). Instead: each user is re-created in the target project
with the SAME uid (critical - Firestore `users/{uid}` docs are keyed by this,
and were already copied with the original uids intact by the Firestore
migration) and a random placeholder password nobody will ever use, then we
generate a password-reset link for each so they can set their own password
the first time they sign in on the new project.

NON-DESTRUCTIVE & IDEMPOTENT: if a uid already exists in the target project
(e.g. re-running after a partial failure), it's skipped rather than
recreated/errored.

Usage (from inventory-backend/):
  python scripts/migrate_auth_users.py            # DRY RUN
  python scripts/migrate_auth_users.py --commit    # apply
"""

import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import firebase_admin  # noqa: E402
from firebase_admin import auth, credentials  # noqa: E402

SOURCE_KEY = "serviceAccountKey-old.json"
TARGET_KEY = "serviceAccountKey.json"


def get_app(key_path, app_name):
    cred = credentials.Certificate(key_path)
    return firebase_admin.initialize_app(cred, name=app_name)


def main():
    commit = "--commit" in sys.argv

    for key in (SOURCE_KEY, TARGET_KEY):
        if not os.path.exists(key):
            print(f"Missing {key} in inventory-backend/")
            sys.exit(1)

    source_app = get_app(SOURCE_KEY, "auth_source")
    target_app = get_app(TARGET_KEY, "auth_target")

    users = list(auth.list_users(app=source_app).iterate_all())
    print(f"Source users found: {len(users)}")
    print(f"Mode: {'COMMIT' if commit else 'DRY RUN'}\n")

    reset_links = []

    for u in users:
        print(f"  {u.uid}  {u.email}  disabled={u.disabled}  email_verified={u.email_verified}")

        if not commit:
            continue

        try:
            auth.get_user(u.uid, app=target_app)
            print(f"    already exists in target - skipping create")
            continue
        except auth.UserNotFoundError:
            pass

        placeholder_password = secrets.token_urlsafe(24)
        auth.create_user(
            uid=u.uid,
            email=u.email,
            email_verified=u.email_verified,
            display_name=u.display_name,
            disabled=u.disabled,
            password=placeholder_password,
            app=target_app,
        )
        link = auth.generate_password_reset_link(u.email, app=target_app)
        reset_links.append((u.email, link))
        print(f"    created + reset link generated")

    if commit and reset_links:
        print("\nPassword reset links (send these to each user, or they can just use 'Forgot password' on the new sign-in page):")
        for email, link in reset_links:
            print(f"  {email}: {link}")

    if not commit:
        print("\nDry run only - pass --commit to actually create users in the target project.")


if __name__ == "__main__":
    main()
