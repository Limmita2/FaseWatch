"""
Парсер документів PDF та DOCX.
"""
import logging

logger = logging.getLogger("document_parser")
MAX_TEXT_LENGTH = 50000


def extract_document_text(file_bytes: bytes, filename: str) -> str | None:
    """Витягує текст з документа за його іменем файлу."""
    filename_lower = filename.lower()

    if filename_lower.endswith(".docx"):
        return _parse_docx(file_bytes)
    elif filename_lower.endswith(".pdf"):
        return _parse_pdf(file_bytes)
    else:
        return None


def _parse_docx(file_bytes: bytes) -> str | None:
    try:
        import io
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        text = "\n".join(paragraphs)
        return text[:MAX_TEXT_LENGTH] if text else None
    except Exception as e:
        logger.error(f"DOCX parse error: {e}")
        return None


def _parse_pdf(file_bytes: bytes) -> str | None:
    try:
        import io
        import pdfplumber
        text_parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        text = "\n".join(text_parts)
        return text[:MAX_TEXT_LENGTH] if text else None
    except Exception as e:
        logger.error(f"PDF parse error: {e}")
        return None
