import base64
import hashlib
import json
from typing import Any

from cryptography.fernet import Fernet

from app.config import settings


def get_fernet() -> Fernet:
    key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_credentials(payload: dict[str, Any]) -> str:
    return get_fernet().encrypt(json.dumps(payload).encode()).decode()


def decrypt_credentials(credentials_json: str | None) -> dict[str, Any]:
    if not credentials_json:
        return {}

    try:
        return json.loads(get_fernet().decrypt(credentials_json.encode()).decode())
    except Exception:
        return json.loads(credentials_json)