"""
File Upload API - Handle strategy document uploads
"""
from fastapi import APIRouter, File, UploadFile, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import structlog

from app.storage.storage_service import get_storage_service
from app.storage.pdf_parser import PDFParser
from app.api.dependencies import get_current_user
from app.models.user import User

logger = structlog.get_logger()

router = APIRouter(prefix="/files", tags=["files"])


class FileUploadResponse(BaseModel):
    """Response after successful file upload."""
    file_url: str
    filename: str
    content_type: str
    size_bytes: int
    extracted_text: Optional[str] = None


class FileDownloadResponse(BaseModel):
    """Response for file download request."""
    content: bytes
    filename: str
    content_type: str


@router.post("/upload", response_model=FileUploadResponse)
async def upload_file(
    file: UploadFile = File(...),
    extract_text: bool = True,
    current_user: User = Depends(get_current_user)
):
    """
    Upload a file (PDF, image, etc.) to storage.
    
    Args:
        file: Uploaded file
        extract_text: Whether to extract text from PDF (default: True)
        current_user: Authenticated user
        
    Returns:
        FileUploadResponse with file URL and metadata
    """
    
    # Validate file type
    allowed_types = ["application/pdf", "image/png", "image/jpeg"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed: {', '.join(allowed_types)}"
        )
    
    # Validate file size (max 10MB)
    max_size = 10 * 1024 * 1024  # 10MB
    file_content = await file.read()
    
    if len(file_content) > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: 10MB"
        )
    
    try:
        # Upload to storage
        storage = get_storage_service()
        
        # Reset file pointer
        await file.seek(0)
        
        file_url = await storage.upload_file(
            file_content=file.file,
            filename=file.filename,
            content_type=file.content_type
        )
        
        # Extract text from PDF if requested
        extracted_text = None
        if extract_text and file.content_type == "application/pdf":
            try:
                parser = PDFParser()
                raw_text = await parser.extract_text(file_content)
                extracted_text = parser.clean_text(raw_text)
                
                logger.info(
                    "pdf_text_extracted",
                    user_id=current_user.id,
                    filename=file.filename,
                    text_length=len(extracted_text)
                )
            except Exception as e:
                logger.warning(
                    "pdf_text_extraction_failed",
                    error=str(e),
                    filename=file.filename
                )
                # Don't fail upload if text extraction fails
        
        logger.info(
            "file_uploaded_successfully",
            user_id=current_user.id,
            filename=file.filename,
            file_url=file_url,
            size_bytes=len(file_content)
        )
        
        return FileUploadResponse(
            file_url=file_url,
            filename=file.filename,
            content_type=file.content_type,
            size_bytes=len(file_content),
            extracted_text=extracted_text
        )
        
    except Exception as e:
        logger.error("file_upload_failed", error=str(e), filename=file.filename)
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("/download")
async def download_file(
    file_url: str,
    current_user: User = Depends(get_current_user)
):
    """
    Download a file from storage.
    
    Args:
        file_url: File URL (from upload response)
        current_user: Authenticated user
        
    Returns:
        File content as bytes
    """
    
    try:
        storage = get_storage_service()
        content = await storage.download_file(file_url)
        
        logger.info(
            "file_downloaded",
            user_id=current_user.id,
            file_url=file_url,
            size_bytes=len(content)
        )
        
        return FileDownloadResponse(
            content=content,
            filename=file_url.split("/")[-1],
            content_type="application/octet-stream"
        )
        
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="File not found")
    except Exception as e:
        logger.error("file_download_failed", error=str(e), file_url=file_url)
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.delete("/delete")
async def delete_file(
    file_url: str,
    current_user: User = Depends(get_current_user)
):
    """
    Delete a file from storage.
    
    Args:
        file_url: File URL (from upload response)
        current_user: Authenticated user
        
    Returns:
        Success message
    """
    
    try:
        storage = get_storage_service()
        deleted = await storage.delete_file(file_url)
        
        if not deleted:
            raise HTTPException(status_code=404, detail="File not found")
        
        logger.info(
            "file_deleted",
            user_id=current_user.id,
            file_url=file_url
        )
        
        return {"message": "File deleted successfully", "file_url": file_url}
        
    except Exception as e:
        logger.error("file_deletion_failed", error=str(e), file_url=file_url)
        raise HTTPException(status_code=500, detail=f"Deletion failed: {str(e)}")

