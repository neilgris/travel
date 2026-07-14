import io
import os

import pillow_heif
from PIL import Image
from werkzeug.datastructures import FileStorage

from app.services.uploads import save_upload, delete_upload

pillow_heif.register_heif_opener()


def _fs(data=b"img", filename="pic.JPG"):
    return FileStorage(stream=io.BytesIO(data), filename=filename,
                       content_type="image/jpeg")


def _heic_bytes(size=(4, 2), color=(200, 30, 40), orientation=None):
    """现造一张小 HEIC 图（可选带 EXIF Orientation 标签）返回其字节。"""
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    save_kwargs = {"format": "HEIF"}
    if orientation is not None:
        exif = Image.Exif()
        exif[0x0112] = orientation  # Orientation
        save_kwargs["exif"] = exif.tobytes()
    img.save(buf, **save_kwargs)
    return buf.getvalue()


def _heic_fs(filename="photo.HEIC", **kwargs):
    return FileStorage(stream=io.BytesIO(_heic_bytes(**kwargs)),
                       filename=filename, content_type="image/heic")


def test_save_upload(tmp_path):
    rel = save_upload(_fs(), str(tmp_path))
    assert rel.startswith("uploads/")
    assert rel.endswith(".jpg")
    assert os.path.exists(os.path.join(str(tmp_path), os.path.basename(rel)))


def test_save_upload_empty_returns_none(tmp_path):
    fs = FileStorage(stream=io.BytesIO(b""), filename="")
    assert save_upload(fs, str(tmp_path)) is None


def test_save_upload_into_subdir(tmp_path):
    rel = save_upload(_fs(), str(tmp_path), subdir="trips/4")
    # 相对路径带子目录，物理文件也落在对应子目录下
    assert rel.startswith("uploads/trips/4/")
    assert os.path.isfile(os.path.join(str(tmp_path), "trips", "4", os.path.basename(rel)))


def test_delete_upload_preserves_subdir(tmp_path):
    rel = save_upload(_fs(), str(tmp_path), subdir="trips/4")
    fpath = os.path.join(str(tmp_path), "trips", "4", os.path.basename(rel))
    assert os.path.isfile(fpath)
    delete_upload(rel, str(tmp_path))
    assert not os.path.exists(fpath)


def test_delete_upload_legacy_flat_path(tmp_path):
    # 兼容历史上存在 uploads/ 根目录的旧路径
    rel = save_upload(_fs(), str(tmp_path))
    fpath = os.path.join(str(tmp_path), os.path.basename(rel))
    assert os.path.isfile(fpath)
    delete_upload(rel, str(tmp_path))
    assert not os.path.exists(fpath)


def test_delete_upload_rejects_traversal(tmp_path):
    # 越界路径（穿越到 upload_folder 之外）应被忽略，不删除外部文件
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("keep me")
    delete_upload("uploads/../secret.txt", str(tmp_path))
    assert outside.exists()


def test_save_upload_heic_converts_to_jpeg(tmp_path):
    # 「照片」App 拖出来常是 HEIC：应被接受、转存为 JPEG，路径与文件名均落 .jpg。
    rel = save_upload(_heic_fs(), str(tmp_path))
    assert rel is not None
    assert rel.endswith(".jpg")
    fpath = os.path.join(str(tmp_path), os.path.basename(rel))
    assert os.path.isfile(fpath)
    with Image.open(fpath) as im:
        assert im.format == "JPEG"


def test_save_upload_heif_extension_also_accepted(tmp_path):
    rel = save_upload(_heic_fs(filename="photo.heif"), str(tmp_path))
    assert rel is not None and rel.endswith(".jpg")


def test_save_upload_heic_applies_exif_orientation(tmp_path):
    # Orientation=6（顺时针 90°）：4x2 的图转码后应按 EXIF 旋转成 2x4，且方向标签清除。
    rel = save_upload(_heic_fs(size=(4, 2), orientation=6), str(tmp_path))
    fpath = os.path.join(str(tmp_path), os.path.basename(rel))
    with Image.open(fpath) as im:
        assert im.size == (2, 4)
        assert im.getexif().get(0x0112, 1) == 1


def test_save_upload_non_heic_kept_as_is(tmp_path):
    # 非 HEIC 图不重新编码，扩展名保持原样。
    rel = save_upload(_fs(data=b"rawbytes", filename="pic.png"), str(tmp_path))
    assert rel.endswith(".png")
    fpath = os.path.join(str(tmp_path), os.path.basename(rel))
    with open(fpath, "rb") as f:
        assert f.read() == b"rawbytes"
