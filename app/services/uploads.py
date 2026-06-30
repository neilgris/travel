import os
import uuid

ALLOWED = {"png", "jpg", "jpeg", "gif", "webp"}


def save_upload(file_storage, upload_folder):
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED:
        return None
    fname = f"{uuid.uuid4().hex}.{ext}"
    os.makedirs(upload_folder, exist_ok=True)
    file_storage.save(os.path.join(upload_folder, fname))
    return f"uploads/{fname}"
