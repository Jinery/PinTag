from pathlib import Path

from cryptography.fernet import Fernet


class EncryptionManager:
    def __init__(self, key_path: str = "encryption.key"):
        self.key_path = Path(key_path)
        self.key = self.load_or_generate_key()
        self.fernet = Fernet(self.key)


    def load_or_generate_key(self) -> bytes:
        if self.key_path.exists():
            with open(self.key_path, "rb") as key_file:
                return key_file.read()
        else:
            key = Fernet.generate_key()
            with open(self.key_path, "wb") as key_file:
                key_file.write(key)
            return key


    def encrypt_file(self, file_data: bytes) -> bytes:
        return self.fernet.encrypt(file_data)


    def decrypt_file(self, encrypted_data: bytes) -> bytes:
        return self.fernet.decrypt(encrypted_data)


encryption_manager = EncryptionManager()