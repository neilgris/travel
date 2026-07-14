import os
import uuid

ALLOWED = {"png", "jpg", "jpeg", "gif", "webp"}


def save_upload(file_storage, upload_folder, subdir=""):
    """把上传文件存到 upload_folder/subdir 下，用随机文件名，返回库里存的相对路径。

    subdir 用于把图片按归属分目录（如 'trips/4'、'people'），避免全挤在 uploads/ 根下。
    subdir 只应由服务端内部拼接（不接受用户直接传值），这里仍规范化并去掉首尾斜杠兜底。
    返回形如 'uploads/trips/4/xxxx.jpg'；无 subdir 时退化为 'uploads/xxxx.jpg'。
    """
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED:
        return None
    fname = f"{uuid.uuid4().hex}.{ext}"
    subdir = (subdir or "").strip("/")
    dest_dir = os.path.join(upload_folder, subdir) if subdir else upload_folder
    os.makedirs(dest_dir, exist_ok=True)
    file_storage.save(os.path.join(dest_dir, fname))
    rel = f"{subdir}/{fname}" if subdir else fname
    return f"uploads/{rel}"


def delete_upload(rel_path, upload_folder):
    """删除 uploads/ 下的一张图；rel_path 形如 'uploads/trips/4/xxx.png'（兼容旧的 'uploads/xxx.png'）。
    保留 uploads/ 之后的子目录结构，规范化后必须仍落在 upload_folder 内（防路径穿越），
    越界忽略；文件不存在则静默跳过。"""
    if not rel_path:
        return
    # 去掉前缀 'uploads/' 保留子路径；异常路径退回只取文件名。
    rel = rel_path.split("uploads/", 1)[-1] if "uploads/" in rel_path else os.path.basename(rel_path)
    root = os.path.normpath(upload_folder)
    fpath = os.path.normpath(os.path.join(root, rel))
    if os.path.commonpath([root, fpath]) != root:
        return
    if os.path.isfile(fpath):
        os.remove(fpath)
