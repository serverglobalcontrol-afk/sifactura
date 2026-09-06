import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from config import settings


def _get_fernet():
    key = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_value(value):
    if not value:
        return None
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt_value(value):
    if not value:
        return None
    try:
        return _get_fernet().decrypt(value.encode()).decode()
    except InvalidToken:
        return None
