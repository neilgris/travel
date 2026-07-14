import io
import os

from werkzeug.datastructures import FileStorage

from app.services.uploads import save_upload, delete_upload


def _fs(data=b"img", filename="pic.JPG"):
    return FileStorage(stream=io.BytesIO(data), filename=filename,
                       content_type="image/jpeg")


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
