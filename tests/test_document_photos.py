import io
import shutil
import zipfile

import pytest
from docx import Document
from PIL import Image

from bp_bot.proposal_document import build_proposal, word_photo
from bp_bot.models import Job
from bp_bot.jobs import Worker
from bp_bot.storage import LocalStorage
from sqlalchemy import select
from test_quotes import patch


def letterhead():
    out = io.BytesIO()
    d = Document()
    d.sections[0].header.paragraphs[0].text = "АТехника"
    d.save(out)
    return out.getvalue()


def photo(fmt="WEBP", mode="RGB"):
    out = io.BytesIO()
    Image.new(mode, (120, 80), (0, 128, 0, 128) if mode == "RGBA" else "green").save(out, format=fmt)
    return out.getvalue()


def view(service):
    qid = service.create(2, patch(), "webp-doc")["id"]
    service.finish(2, qid, 1)
    v = service.view(2, qid)
    v["payload"]["items"][0]["profile"] = {"image_key": "photos/test.webp"}
    v["_images"] = {"photos/test.webp": photo()}
    return v


@pytest.mark.parametrize("fmt,mode", [("WEBP", "RGB"), ("WEBP", "RGBA"), ("JPEG", "RGB"), ("PNG", "RGBA")])
def test_photos_become_word_readable_png_without_resizing(fmt, mode):
    image = Image.open(word_photo(photo(fmt, mode)))
    assert image.format == "PNG"
    assert image.size == (120, 80)
    assert image.mode == mode


def test_proposal_embeds_webp_photo_as_png(service, tmp_path):
    path = tmp_path / "photo.docx"
    build_proposal(letterhead(), view(service), path)
    doc = Document(path)
    assert len(doc.inline_shapes) == 1
    assert doc.sections[0].header.paragraphs[0].text == "АТехника"
    with zipfile.ZipFile(path) as z:
        assert any(name.endswith(".png") for name in z.namelist() if name.startswith("word/media/"))


@pytest.mark.skipif(not shutil.which("soffice"), reason="LibreOffice not installed")
def test_webp_photo_generates_actual_word_and_pdf(service, tmp_path):
    v = view(service)
    store = LocalStorage(tmp_path)
    store.put("letterheads/test.docx", letterhead(), "application/octet-stream")
    store.put("photos/test.webp", photo(), "image/webp")
    from bp_bot.models import Version

    with service.sessions.begin() as s:
        version = s.scalar(select(Version).where(Version.quote_id == v["id"]))
        version.payload = v["payload"]
    service.request_files(2, v["id"], 1)
    worker = Worker(service.sessions, store)
    assert worker.once()
    with service.sessions() as s:
        job = s.scalar(select(Job))
        assert job.state == "done", job.error
        word = store.get(job.docx_key)
        pdf = store.get(job.pdf_key)
    assert len(Document(io.BytesIO(word)).inline_shapes) == 1
    assert pdf.startswith(b"%PDF")


def test_failure_logs_do_not_expose_exception_data(service, tmp_path, caplog):
    v = view(service)
    service.request_files(2, v["id"], 1)
    worker = Worker(service.sessions, LocalStorage(tmp_path))
    worker.once()
    assert "stage=letterhead_read" in caplog.text
    assert "FileNotFoundError" in caplog.text
    assert "letterheads/test.docx" not in caplog.text
