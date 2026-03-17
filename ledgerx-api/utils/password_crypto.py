from cryptography.fernet import Fernet
from core.config import settings

fernet = Fernet(settings.FERNET_KEY)

def encrypt_password(password: str) -> bytes:
    return fernet.encrypt(password.encode())


def decrypt_password(token: bytes) -> str:
    return fernet.decrypt(token).decode()