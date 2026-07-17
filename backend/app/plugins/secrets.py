import base64
import hashlib

from cryptography.fernet import Fernet


class SecretBox:
    def __init__(self, app_secret_key: str):
        digest = hashlib.sha256(
            f"meetflow-plugin-config:{app_secret_key}".encode()
        ).digest()
        self.fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        return self.fernet.decrypt(value.encode()).decode()
