import hashlib
import os
from datetime import datetime
from pathlib import Path

class FileManager:
    def __init__(self, base_path="users_files"):
        self.base_path = Path(base_path)
        self.temp_path = self.base_path / "temp"
        self.setup_directories()


    def setup_directories(self):
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.temp_path.mkdir(parents=True, exist_ok=True)


    def get_user_folder(self, user_id: int, file_type: str) -> Path:
        user_path = self.base_path / str(user_id) / file_type
        user_path.mkdir(parents=True, exist_ok=True)
        return user_path


    def generate_filename(self, original_filename: str, user_id: int) -> str:
        timestamp = int(datetime.now().timestamp())
        file_ext = Path(original_filename).suffix if original_filename else '.bin'
        return f"{user_id}_{timestamp}_{hashlib.md5(original_filename.encode()).hexdigest()[:8]}{file_ext}"


    def save_file(self, file_data: bytes, user_id: int, file_type: str, original_filename: str = None) -> str:
        if original_filename is None:
            original_filename = self.generate_filename(original_filename, user_id)

        user_folder = self.get_user_folder(user_id, file_type)
        file_path = user_folder / original_filename

        with open(file_path, "wb") as f:
            f.write(file_data)

        return str(file_path)


    def get_file(self, file_path: str) -> bytes:
        path_to_file = Path(file_path)
        if path_to_file.exists():
            if path_to_file.is_file():
                with open(path_to_file, "rb") as f:
                    return f.read()

        raise FileNotFoundError(f"File not found: {path_to_file}")


    def delete_file(self, file_path: str):
        path_to_file = Path(file_path)
        if path_to_file.exists():
            if path_to_file.is_file():
                os.remove(path_to_file)
                return
        raise FileNotFoundError(f"File not found: {path_to_file}")


    def get_file_size(self, file_path: str) -> int:
        return Path(file_path).stat().st_size


file_manager = FileManager()