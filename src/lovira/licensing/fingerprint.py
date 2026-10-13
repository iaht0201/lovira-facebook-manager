"""
Lovira-Facebook Manager
Định danh thiết bị (Device Fingerprint)
Kết hợp Install ID bền vững và băm thông tin hệ máy để định danh thiết bị (AC-23, AC-24).
"""

import hashlib
import platform
import uuid
from pathlib import Path


def get_or_create_device_id(storage_path: Path) -> str:
    """Lấy hoặc tạo Install ID bền vững cho thiết bị."""
    storage_path.mkdir(parents=True, exist_ok=True)
    device_id_file = storage_path / ".device_id"

    if device_id_file.exists():
        try:
            device_id = device_id_file.read_text(encoding="utf-8").strip()
            if device_id:
                return device_id
        except OSError:
            pass

    # Tạo UUID ngẫu nhiên mới
    new_id = f"dev_{uuid.uuid4().hex}"
    try:
        device_id_file.write_text(new_id, encoding="utf-8")
    except OSError:
        pass
    return new_id


def get_device_fingerprint(device_id: str) -> str:
    """Tạo digest định danh kết hợp giữa install ID và đặc tính hệ máy."""
    raw_info = f"{device_id}:{platform.system()}:{platform.machine()}:{platform.processor()}"
    return hashlib.sha256(raw_info.encode("utf-8")).hexdigest()[:32]
