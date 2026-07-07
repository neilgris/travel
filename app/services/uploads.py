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


def delete_upload(rel_path, upload_folder):
    """删除 uploads/ 下的一张图；rel_path 形如 'uploads/xxx.png'。
    只按文件名在 upload_folder 内删除，越界路径忽略；文件不存在则静默跳过。"""
    if not rel_path:
        return
    fname = os.path.basename(rel_path)
    fpath = os.path.join(upload_folder, fname)
    if os.path.exists(fpath):
        os.remove(fpath)
