import hashlib
import secrets


def make_password_hash(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def verify_password(password: str, password_hash: str) -> bool:
    current_hash = make_password_hash(password)
    return secrets.compare_digest(current_hash, password_hash)