import os
import uuid

import pillow_heif
from PIL import Image, ImageOps

# HEIC/HEIF 由 pillow-heif 注册进 Pillow 后可解码，转存为 JPEG（Chrome 不认 HEIC）。
pillow_heif.register_heif_opener()

ALLOWED = {"png", "jpg", "jpeg", "gif", "webp"}
HEIC_EXTS = {"heic", "heif"}


def save_upload(file_storage, upload_folder, subdir=""):
    """把上传文件存到 upload_folder/subdir 下，用随机文件名，返回库里存的相对路径。

    subdir 用于把图片按归属分目录（如 'trips/4'、'people'），避免全挤在 uploads/ 根下。
    subdir 只应由服务端内部拼接（不接受用户直接传值），这里仍规范化并去掉首尾斜杠兜底。
    HEIC/HEIF（Mac「照片」拖出来常见）会按 EXIF 方向转正后转存为 JPEG，文件名与路径落 .jpg；
    其它受支持格式原样保存。返回形如 'uploads/trips/4/xxxx.jpg'；无 subdir 时退化为 'uploads/xxxx.jpg'。
    """
    if not file_storage or not file_storage.filename:
        return None
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    is_heic = ext in HEIC_EXTS
    if ext not in ALLOWED and not is_heic:
        return None
    out_ext = "jpg" if is_heic else ext
    fname = f"{uuid.uuid4().hex}.{out_ext}"
    subdir = (subdir or "").strip("/")
    dest_dir = os.path.join(upload_folder, subdir) if subdir else upload_folder
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, fname)
    if is_heic:
        # 解码 HEIC → 按 EXIF 旋转（避免照片躺倒）→ 存为 JPEG，方向标签一并清除。
        with Image.open(file_storage.stream) as im:
            im = ImageOps.exif_transpose(im)
            im.convert("RGB").save(dest, format="JPEG", quality=90)
    else:
        file_storage.save(dest)
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
