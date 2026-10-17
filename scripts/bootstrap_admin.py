"""
Create (or repair) the first admin account on a clean project.

Self-registration is locked to `status: 'pending'` by firestore.rules, so the
very first admin has to be created with the Admin SDK. Password is read from
the ADMIN_PASSWORD env var so it is never stored in the repo.

Usage (from inventory-backend/):
  ADMIN_EMAIL=a@b.com ADMIN_NAME="Full Name" ADMIN_PASSWORD=... \
    python scripts/bootstrap_admin.py --commit
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from firebase_admin import auth as fb_auth  # noqa: E402
from firebase_admin import firestore as fb_fs  # noqa: E402

from db.connection import get_db  # noqa: E402

COMMIT = "--commit" in sys.argv
email = os.environ["ADMIN_EMAIL"].strip().lower()
name = os.environ.get("ADMIN_NAME", "Admin")
password = os.environ["ADMIN_PASSWORD"]

PERMS = {
    "inventoryView": True, "inventoryAdjust": True, "recipePrepare": True,
    "inspectionSubmit": True, "notificationsView": True, "forecastView": True, "staffManage": True,
}

db = get_db()
try:
    uid = fb_auth.get_user_by_email(email).uid
    print(f"auth EXISTS  {email} (uid={uid})")
except fb_auth.UserNotFoundError:
    if not COMMIT:
        print(f"DRY RUN: would create {email}")
        sys.exit(0)
    uid = fb_auth.create_user(email=email, password=password, display_name=name).uid
    print(f"auth CREATED {email} (uid={uid})")

if COMMIT:
    db.collection("users").document(uid).set({
        "uid": uid, "email": email, "fullName": name, "role": "admin", "status": "active",
        "phoneNumber": "", "unitPreference": "Metric (g/ml)", "isActive": True, "shiftOn": False,
        "isArchived": False, "mustChangePassword": True, "permissions": PERMS, "photoUrl": "",
        "createdAt": fb_fs.SERVER_TIMESTAMP,
    }, merge=True)
    print(f"firestore SET users/{uid} role=admin status=active")
