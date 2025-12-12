"""
Storage Service - Abstraction for Local Disk (dev) and S3 (prod)
"""
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO, Optional
import asyncio
import structlog
import uuid
import os

logger = structlog.get_logger()


class StorageService(ABC):
    """Abstract storage service interface."""
    
    @abstractmethod
    async def upload_file(
        self,
        file_content: BinaryIO,
        filename: str,
        content_type: str
    ) -> str:
        """
        Upload a file and return its URL/path.
        
        Args:
            file_content: File binary content
            filename: Original filename
            content_type: MIME type (e.g., application/pdf)
            
        Returns:
            URL or path to access the file
        """
        pass
    
    @abstractmethod
    async def download_file(self, file_url: str) -> bytes:
        """
        Download a file by URL/path.
        
        Args:
            file_url: URL or path to the file
            
        Returns:
            File content as bytes
        """
        pass
    
    @abstractmethod
    async def delete_file(self, file_url: str) -> bool:
        """
        Delete a file by URL/path.
        
        Args:
            file_url: URL or path to the file
            
        Returns:
            True if deleted successfully
        """
        pass


class LocalDiskStorage(StorageService):
    """
    Local disk storage for development.
    Stores files in a volume-mounted directory.
    """
    
    def __init__(self, base_path: str = "/app/storage/uploads"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info("local_disk_storage_initialized", path=str(self.base_path))
    
    async def upload_file(
        self,
        file_content: BinaryIO,
        filename: str,
        content_type: str
    ) -> str:
        """Save file to local disk and return relative path."""
        
        # Generate unique filename
        file_ext = Path(filename).suffix
        unique_name = f"{uuid.uuid4()}{file_ext}"
        
        # Create subdirectory by content type
        subdir = self._get_subdir(content_type)
        upload_dir = self.base_path / subdir
        
        # Read file content first (can be sync, it's in-memory)
        content = file_content.read()
        
        # Offload blocking file I/O to thread pool
        await asyncio.to_thread(self._write_file_sync, upload_dir, unique_name, content)
        
        # Return relative path
        relative_path = f"uploads/{subdir}/{unique_name}"
        
        logger.info(
            "file_uploaded_local",
            original_name=filename,
            stored_name=unique_name,
            size_bytes=len(content),
            path=relative_path
        )
        
        return relative_path
    
    def _write_file_sync(self, upload_dir: Path, filename: str, content: bytes):
        """Synchronous file write (called from thread pool)."""
        upload_dir.mkdir(parents=True, exist_ok=True)
        file_path = upload_dir / filename
        with open(file_path, "wb") as f:
            f.write(content)
    
    async def download_file(self, file_url: str) -> bytes:
        """Read file from local disk."""
        
        # file_url is relative path like "uploads/pdfs/uuid.pdf"
        # Construct absolute path: /app/storage + /uploads/pdfs/uuid.pdf
        file_path = Path("/app/storage") / file_url
        
        # Offload blocking file I/O to thread pool
        return await asyncio.to_thread(self._read_file_sync, file_path, file_url)
    
    def _read_file_sync(self, file_path: Path, file_url: str) -> bytes:
        """Synchronous file read (called from thread pool)."""
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_url}")
        
        with open(file_path, "rb") as f:
            content = f.read()
        
        logger.debug("file_downloaded_local", path=file_url, size_bytes=len(content))
        return content
    
    async def delete_file(self, file_url: str) -> bool:
        """Delete file from local disk."""
        
        # Construct absolute path
        file_path = Path("/app/storage") / file_url
        
        # Offload blocking file I/O to thread pool
        return await asyncio.to_thread(self._delete_file_sync, file_path, file_url)
    
    def _delete_file_sync(self, file_path: Path, file_url: str) -> bool:
        """Synchronous file delete (called from thread pool)."""
        if file_path.exists():
            file_path.unlink()
            logger.info("file_deleted_local", path=file_url)
            return True
        
        logger.warning("file_not_found_for_deletion", path=file_url)
        return False
    
    def _get_subdir(self, content_type: str) -> str:
        """Determine subdirectory based on content type."""
        if content_type == "application/pdf":
            return "pdfs"
        elif content_type.startswith("image/"):
            return "images"
        else:
            return "documents"


class S3Storage(StorageService):
    """
    S3 storage for production.
    Uses boto3 to interact with AWS S3.
    """
    
    def __init__(
        self,
        bucket_name: str,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region_name: str = "us-east-1"
    ):
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for S3Storage. "
                "Install with: pip install boto3"
            )
        
        self.bucket_name = bucket_name
        
        # Initialize S3 client
        if aws_access_key_id and aws_secret_access_key:
            self.s3_client = boto3.client(
                "s3",
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=region_name
            )
        else:
            # Use IAM role (production)
            self.s3_client = boto3.client("s3", region_name=region_name)
        
        logger.info("s3_storage_initialized", bucket=bucket_name, region=region_name)
    
    async def upload_file(
        self,
        file_content: BinaryIO,
        filename: str,
        content_type: str
    ) -> str:
        """Upload file to S3 and return URL."""
        
        # Generate unique S3 key
        file_ext = Path(filename).suffix
        unique_name = f"{uuid.uuid4()}{file_ext}"
        
        # Create S3 key with prefix
        prefix = self._get_prefix(content_type)
        s3_key = f"{prefix}/{unique_name}"
        
        # Read file content
        content = file_content.read()
        
        # Offload blocking boto3 call to thread pool
        await asyncio.to_thread(
            self.s3_client.put_object,
            Bucket=self.bucket_name,
            Key=s3_key,
            Body=content,
            ContentType=content_type
        )
        
        # Return S3 URL
        s3_url = f"s3://{self.bucket_name}/{s3_key}"
        
        logger.info(
            "file_uploaded_s3",
            original_name=filename,
            s3_key=s3_key,
            size_bytes=len(content),
            url=s3_url
        )
        
        return s3_url
    
    async def download_file(self, file_url: str) -> bytes:
        """Download file from S3."""
        
        # Parse S3 URL: s3://bucket/key
        if not file_url.startswith("s3://"):
            raise ValueError(f"Invalid S3 URL: {file_url}")
        
        parts = file_url.replace("s3://", "").split("/", 1)
        bucket = parts[0]
        key = parts[1]
        
        # Offload blocking boto3 call to thread pool
        response = await asyncio.to_thread(
            self.s3_client.get_object,
            Bucket=bucket,
            Key=key
        )
        content = response["Body"].read()
        
        logger.debug("file_downloaded_s3", url=file_url, size_bytes=len(content))
        
        return content
    
    async def delete_file(self, file_url: str) -> bool:
        """Delete file from S3."""
        
        # Parse S3 URL
        if not file_url.startswith("s3://"):
            raise ValueError(f"Invalid S3 URL: {file_url}")
        
        parts = file_url.replace("s3://", "").split("/", 1)
        bucket = parts[0]
        key = parts[1]
        
        try:
            # Offload blocking boto3 call to thread pool
            await asyncio.to_thread(
                self.s3_client.delete_object,
                Bucket=bucket,
                Key=key
            )
            logger.info("file_deleted_s3", url=file_url)
            return True
        except Exception as e:
            logger.error("s3_delete_failed", url=file_url, error=str(e))
            return False
    
    def _get_prefix(self, content_type: str) -> str:
        """Determine S3 prefix based on content type."""
        if content_type == "application/pdf":
            return "strategy-documents/pdfs"
        elif content_type.startswith("image/"):
            return "strategy-documents/images"
        else:
            return "strategy-documents/other"


def get_storage_service() -> StorageService:
    """
    Factory function to get storage service based on environment.
    
    Returns:
        StorageService instance (LocalDiskStorage or S3Storage)
    """
    from app.config import settings
    
    storage_backend = os.getenv("STORAGE_BACKEND", "local")  # local | s3
    
    if storage_backend == "s3":
        # Production: Use S3
        bucket_name = os.getenv("S3_BUCKET_NAME", "trading-platform-documents")
        aws_access_key_id = os.getenv("AWS_ACCESS_KEY_ID")
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY")
        region = os.getenv("AWS_REGION", "us-east-1")
        
        return S3Storage(
            bucket_name=bucket_name,
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region
        )
    else:
        # Development: Use local disk
        base_path = os.getenv("LOCAL_STORAGE_PATH", "/app/storage/uploads")
        return LocalDiskStorage(base_path=base_path)

