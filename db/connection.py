import json
import os
import firebase_admin
from firebase_admin import credentials, firestore
from dotenv import load_dotenv

load_dotenv()

def get_db():
    if not firebase_admin._apps:
        service_account_env = os.getenv("FIREBASE_SERVICE_ACCOUNT")
        if service_account_env:
            cred = credentials.Certificate(json.loads(service_account_env))
        else:
            cred = credentials.Certificate(os.getenv("FIREBASE_CREDENTIALS", "serviceAccountKey.json"))
        firebase_admin.initialize_app(cred)
    return firestore.client()
