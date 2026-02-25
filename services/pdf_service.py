import io
import logging
import pdfplumber

logger = logging.getLogger(__name__)

class PDFExtractionError(Exception):
    """Raised when text extraction from a PDF fails."""

def extract_text_from_bytes(pdf_bytes: bytes) -> str:
    """Extract all text from every page of a PDF."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if not pdf.pages:
                raise PDFExtractionError("PDF has no pages.")

            pages_text = []
            for page in pdf.pages:
                text = page.extract_text() or ""
                pages_text.append(text)

            full_text = "\f".join(pages_text).strip()
            if not full_text:
                raise PDFExtractionError("No readable text found in the PDF.")

            return full_text
    except PDFExtractionError:
        raise
    except Exception as exc:
        raise PDFExtractionError(f"Failed to parse PDF: {exc}")
