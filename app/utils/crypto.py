import base64
import hashlib
import json
from typing import Any, Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.config import settings


def _derive_fernet_key(secret: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=600_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(secret.encode()))


def get_fernet() -> Fernet:
    secret = settings.encryption_key or settings.secret_key
    return Fernet(_derive_fernet_key(secret, b"anywhere2opus-fernet-v1"))


def get_legacy_fernet() -> Fernet:
    key_bytes = hashlib.sha256(settings.secret_key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key_bytes))


def encrypt_credentials(payload: dict[str, Any]) -> str:
    return get_fernet().encrypt(json.dumps(payload).encode()).decode()


def decrypt_credentials(credentials_json: Optional[str]) -> dict[str, Any]:
    if not credentials_json:
        return {}

    try:
        return json.loads(get_fernet().decrypt(credentials_json.encode()).decode())
    except Exception:
        try:
            return json.loads(get_legacy_fernet().decrypt(credentials_json.encode()).decode())
        except Exception:
            return json.loads(credentials_json)