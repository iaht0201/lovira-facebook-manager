"""
Lovira-Facebook Manager
Kho lưu trữ bí mật (Secret Vault)
- Ưu tiên sử dụng OS Keyring (Windows Credential Manager / Linux SecretService)
- Fallback an toàn với AES-256-GCM khi Keyring không khả dụng (AC-33)
- Tuyệt đối không lưu mật khẩu/token dưới dạng Plain Text
"""

import base64
import json
import os
from pathlib import Path
from typing import Optional
import keyring
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


class SecretVault:
    """Quản lý lưu trữ và truy xuất các thông tin xác thực nhạy cảm."""

    SERVICE_NAME = "LoviraFacebookManager"

    def __init__(self, fallback_vault_dir: Path | None = None):
        self.fallback_vault_dir = fallback_vault_dir
        self._master_key: Optional[bytes] = None

    def _get_or_create_master_key(self) -> bytes:
        """Lấy hoặc tạo khóa AES-256 chủ cho local fallback vault."""
        if self._master_key is not None:
            return self._master_key

        if self.fallback_vault_dir is None:
            raise RuntimeError("Fallback vault directory chưa được cấu hình.")

        self.fallback_vault_dir.mkdir(parents=True, exist_ok=True)
        key_file = self.fallback_vault_dir / ".vault_key"

        if key_file.exists():
            self._master_key = key_file.read_bytes()
        else:
            # Sinh khóa 256-bit ngẫu nhiên
            self._master_key = AESGCM.generate_key(bit_length=256)
            key_file.write_bytes(self._master_key)
            # Khóa quyền đọc ghi trên file key nếu là Unix
            try:
                os.chmod(key_file, 0o600)
            except OSError:
                pass

        return self._master_key

    def set_secret(self, key_name: str, secret_value: str) -> str:
        """Lưu trữ secret. Trả về tên provider đã lưu ('keyring' hoặc 'local_vault')."""
        # 1. Thử lưu vào OS Keyring
        try:
            keyring.set_password(self.SERVICE_NAME, key_name, secret_value)
            # Kiểm tra đọc lại để chắc chắn keyring hoạt động
            verified = keyring.get_password(self.SERVICE_NAME, key_name)
            if verified == secret_value:
                return "keyring"
        except Exception:
            pass

        # 2. Nếu Keyring không khả dụng (AC-33), sử dụng AES-256-GCM mã hóa
        master_key = self._get_or_create_master_key()
        aesgcm = AESGCM(master_key)
        nonce = os.urandom(12)
        ciphertext = aesgcm.encrypt(nonce, secret_value.encode("utf-8"), key_name.encode("utf-8"))

        payload = {
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "data": base64.b64encode(ciphertext).decode("ascii"),
        }

        vault_file = self.fallback_vault_dir / f"{key_name}.enc"
        vault_file.write_text(json.dumps(payload), encoding="utf-8")
        try:
            os.chmod(vault_file, 0o600)
        except OSError:
            pass

        return "local_vault"

    def get_secret(self, key_name: str) -> Optional[str]:
        """Truy xuất secret đã lưu."""
        # 1. Thử từ OS Keyring
        try:
            val = keyring.get_password(self.SERVICE_NAME, key_name)
            if val is not None:
                return val
        except Exception:
            pass

        # 2. Thử từ local AES-256-GCM vault
        if self.fallback_vault_dir is not None:
            vault_file = self.fallback_vault_dir / f"{key_name}.enc"
            if vault_file.exists():
                try:
                    payload = json.loads(vault_file.read_text(encoding="utf-8"))
                    nonce = base64.b64decode(payload["nonce"])
                    ciphertext = base64.b64decode(payload["data"])

                    master_key = self._get_or_create_master_key()
                    aesgcm = AESGCM(master_key)
                    decrypted = aesgcm.decrypt(nonce, ciphertext, key_name.encode("utf-8"))
                    return decrypted.decode("utf-8")
                except Exception:
                    return None

        return None

    def delete_secret(self, key_name: str) -> bool:
        """Xóa secret."""
        deleted = False
        try:
            keyring.delete_password(self.SERVICE_NAME, key_name)
            deleted = True
        except Exception:
            pass

        if self.fallback_vault_dir is not None:
            vault_file = self.fallback_vault_dir / f"{key_name}.enc"
            if vault_file.exists():
                try:
                    vault_file.unlink()
                    deleted = True
                except OSError:
                    pass

        return deleted
