import io
import logging
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from core.database import get_db
from services.pdf_service import PDFExtractionError
from services.process_service import process_invoice
from api.deps import RoleChecker
from utils.email_utils import send_invoice_processed_email
from utils.pdf_utils import read_pdf_bytes

router  = APIRouter(prefix="/process", tags=["Invoice Reconciliation"])
logger  = logging.getLogger(__name__)

@router.post("", summary="Process PDF invoice (Email result)")
async def process(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    db: Session = Depends(get_db),
    current_user: dict = Depends(RoleChecker("ai-analyze", "view"))
):
    try:
        pdf_bytes = await read_pdf_bytes(file)
        user_email = current_user.get("email", "example@gmail.com")
        result = process_invoice(file.filename or "invoice.pdf", pdf_bytes, db)
        
        # Check Guardrails
        if not result.parsed_billing.is_valid:
            raise HTTPException(400, result.parsed_billing.validation_reason or "Kami tidak mendeteksi invoice yang valid.")

        if result.analysis:
            background_tasks.add_task(
                send_invoice_processed_email,
                user_email,
                file.filename or "invoice.pdf",
                result.analysis,
                result.csv_content
            )
            
        return {
            "status": "success",
            "message": "Invoice processed. Full report has been sent to your email.",
            "filename": file.filename or "invoice.pdf",
            "recipient": user_email
        }
    except Exception as e:
        # 1. Custom/Guardrail errors -> 400
        if "HTTPException" in type(e).__name__ or isinstance(e, (PDFExtractionError, ValueError)):
            detail = getattr(e, "detail", str(e))
            raise HTTPException(400, detail)
        
        # 2. Database Connectivity Errors -> 503
        if "OperationalError" in type(e).__name__:
            logger.error(f"[DB ERROR] Connection timed out: {str(e)}")
            raise HTTPException(503, "Database is unreachable. Please check your VPN or DB server.")

        # 3. Everything else -> 500
        logger.exception("process_invoice fatal error")
        raise HTTPException(500, "Internal Server Error during processing.")

@router.post("/csv", summary="Process PDF invoice (Download CSV result)")
async def process_csv(
    file: UploadFile = File(...), 
    db: Session = Depends(get_db),
    current_user: dict = Depends(RoleChecker("ai-analyze", "view"))
):
    """
    Processes the uploaded PDF and returns the reconciliation CSV directly as a download.
    """
    try:
        pdf_bytes = await read_pdf_bytes(file)
        result = process_invoice(file.filename or "invoice.pdf", pdf_bytes, db)
        
        # Check Guardrails
        if not result.parsed_billing.is_valid:
            raise HTTPException(400, result.parsed_billing.validation_reason or "Dokumen bukan merupakan invoice valid.")

        if not result.csv_content:
             raise HTTPException(404, "No billing data found to generate CSV.")

        # Prepare CSV for download (with BOM and sep=, for Excel)
        csv_with_bom = "\ufeffsep=,\n" + result.csv_content
        
        filename = (file.filename or "invoice.pdf").rsplit('.', 1)[0]
        headers = {
            'Content-Disposition': f'attachment; filename="reconciliation_{filename}.csv"',
            'Access-Control-Expose-Headers': 'Content-Disposition'
        }
        
        return StreamingResponse(
            iter([csv_with_bom]), 
            media_type="text/csv", 
            headers=headers
        )
    except Exception as e:
        # 1. Custom/Guardrail errors -> 400
        if "HTTPException" in type(e).__name__ or isinstance(e, (PDFExtractionError, ValueError)):
            detail = getattr(e, "detail", str(e))
            raise HTTPException(400, detail)
            
        # 2. Database Connectivity Errors -> 503
        if "OperationalError" in type(e).__name__:
            logger.error(f"[DB ERROR] CSV connection timed out: {str(e)}")
            raise HTTPException(503, "Database is unreachable. Please check your VPN or DB server connection.")

        # 3. Everything else -> 500
        logger.exception("process_csv fatal error")
        raise HTTPException(500, "Internal Server Error during CSV processing.")
