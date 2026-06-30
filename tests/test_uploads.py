import io
import os

from werkzeug.datastructures import FileStorage

from app.services.uploads import save_upload


def test_save_upload(tmp_path):
    fs = FileStorage(
        stream=io.BytesIO(b"img"),
        filename="pic.JPG",
        content_type="image/jpeg"
    )
    rel = save_upload(fs, str(tmp_path))
    assert rel.startswith("uploads/")
    assert rel.endswith(".jpg")
    assert os.path.exists(os.path.join(str(tmp_path), os.path.basename(rel)))


def test_save_upload_empty_returns_none(tmp_path):
    fs = FileStorage(stream=io.BytesIO(b""), filename="")
    assert save_upload(fs, str(tmp_path)) is None
