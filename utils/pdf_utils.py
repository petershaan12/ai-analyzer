from fastapi import UploadFile, HTTPException
from core.config import get_settings

settings = get_settings()
_MAX_BYTES = settings.max_pdf_size_mb * 1024 * 1024

async def read_pdf_bytes(file: UploadFile) -> bytes:
    """Reads PDF UploadFile into bytes and validates file size/type."""
    if file.content_type != "application/pdf":
        raise HTTPException(400, f"Only PDF accepted. Got: {file.content_type}")
    
    data = await file.read()
    
    if not data:
        raise HTTPException(400, "File is empty.")
    if len(data) > _MAX_BYTES:
        raise HTTPException(400, f"File too large. Max {settings.max_pdf_size_mb} MB.")
        
    return data
