from pathlib import Path
from typing import List, Dict, Any
import pypdf
import docx


class ExtractionError(Exception):
    """Raised when text cannot be extracted from a file."""
    pass


def extract_document(file_path: Path | str) -> List[Dict[str, Any]]:
    """
    Extracts text from supported offline document formats (PDF, DOCX, TXT/MD).
    Returns a list of page/section segments:
    [{"page": 1, "text": "Page content..."}, ...]
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return _extract_pdf(path)
    elif suffix in (".docx", ".doc"):
        if suffix == ".doc":
            raise ExtractionError("Legacy binary .doc format is not supported. Please convert to .docx or .pdf.")
        return _extract_docx(path)
    elif suffix in (".txt", ".md", ".json", ".csv"):
        return _extract_plain_text(path)
    elif suffix in (".png", ".jpg", ".jpeg", ".tiff", ".bmp", ".webp"):
        raise ExtractionError("Image OCR is disabled in v1 for 100% offline self-contained portability.")
    else:
        raise ExtractionError(f"Unsupported file format: {suffix}. Supported formats: PDF, DOCX, TXT, MD.")


def _extract_pdf(path: Path) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    try:
        reader = pypdf.PdfReader(str(path))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception:
                raise ExtractionError("PDF is password-protected and cannot be decrypted.")

        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            text = text.strip()
            if text:
                segments.append({
                    "page": i + 1,
                    "text": text
                })

        if not segments:
            raise ExtractionError("No readable text found in PDF. It might be scanned/empty.")

        return segments
    except ExtractionError:
        raise
    except Exception as e:
        raise ExtractionError(f"Failed to read PDF '{path.name}': {str(e)}")


def _extract_docx(path: Path) -> List[Dict[str, Any]]:
    segments: List[Dict[str, Any]] = []
    try:
        doc = docx.Document(str(path))
        # Group paragraphs into logical sections (~500 words per section) to mimic pages
        current_section: List[str] = []
        current_len = 0
        section_idx = 1

        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            current_section.append(text)
            current_len += len(text)
            if current_len >= 1200:
                segments.append({
                    "page": section_idx,
                    "text": "\n".join(current_section)
                })
                current_section = []
                current_len = 0
                section_idx += 1

        if current_section:
            segments.append({
                "page": section_idx,
                "text": "\n".join(current_section)
            })

        # Also extract table text if present
        for t_idx, table in enumerate(doc.tables):
            table_lines = []
            for row in table.rows:
                row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
                if row_text:
                    table_lines.append(row_text)
            if table_lines:
                segments.append({
                    "page": section_idx + t_idx,
                    "text": "Table Data:\n" + "\n".join(table_lines)
                })

        if not segments:
            raise ExtractionError("No readable text found in DOCX file.")

        return segments
    except ExtractionError:
        raise
    except Exception as e:
        raise ExtractionError(f"Failed to read DOCX '{path.name}': {str(e)}")


def _extract_plain_text(path: Path) -> List[Dict[str, Any]]:
    try:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
        if not content:
            raise ExtractionError("File is empty.")
        return [{"page": 1, "text": content}]
    except ExtractionError:
        raise
    except Exception as e:
        raise ExtractionError(f"Failed to read text file '{path.name}': {str(e)}")
