import pytest
from pathlib import Path
from app.services.extractor import extract_document, ExtractionError


def test_extract_docx_sample():
    docx_path = Path("samples/nda_agreement.docx")
    assert docx_path.exists(), "Sample docx must exist"
    segments = extract_document(docx_path)
    assert len(segments) >= 1
    assert "MUTUAL NON-DISCLOSURE AGREEMENT" in segments[0]["text"]
    assert "Delaware" in segments[0]["text"]


def test_extract_pdf_sample():
    pdf_path = Path("samples/commercial_lease.pdf")
    assert pdf_path.exists(), "Sample pdf must exist"
    segments = extract_document(pdf_path)
    assert len(segments) >= 1
    assert "SUBLEASE AGREEMENT" in segments[0]["text"]
    assert segments[0]["page"] == 1


def test_extract_nonexistent_file():
    with pytest.raises(FileNotFoundError):
        extract_document("samples/does_not_exist.docx")


def test_extract_unsupported_format(tmp_path):
    bad_file = tmp_path / "test.xyz"
    bad_file.write_text("dummy")
    with pytest.raises(ExtractionError, match="Unsupported file format"):
        extract_document(bad_file)


def test_extract_empty_file(tmp_path):
    empty_file = tmp_path / "empty.txt"
    empty_file.write_text("")
    with pytest.raises(ExtractionError, match="File is empty"):
        extract_document(empty_file)
