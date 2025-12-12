"""
PDF Parser - Extract text from PDF documents
"""
import structlog
from typing import Optional

logger = structlog.get_logger()


class PDFParser:
    """Parse PDF files and extract text content."""
    
    def __init__(self):
        try:
            import pdfplumber
            self.pdfplumber = pdfplumber
        except ImportError:
            raise ImportError(
                "pdfplumber is required for PDF parsing. "
                "Install with: pip install pdfplumber"
            )
    
    async def extract_text(self, pdf_content: bytes) -> str:
        """
        Extract text from PDF bytes.
        
        Args:
            pdf_content: PDF file content as bytes
            
        Returns:
            Extracted text as string
        """
        import io
        
        try:
            text_parts = []
            
            with self.pdfplumber.open(io.BytesIO(pdf_content)) as pdf:
                logger.info("parsing_pdf", pages=len(pdf.pages))
                
                for i, page in enumerate(pdf.pages, 1):
                    page_text = page.extract_text()
                    
                    if page_text:
                        text_parts.append(page_text)
                        logger.debug(f"extracted_page", page=i, chars=len(page_text))
                
                full_text = "\n\n".join(text_parts)
                
                logger.info(
                    "pdf_parsed_successfully",
                    pages=len(pdf.pages),
                    total_chars=len(full_text)
                )
                
                return full_text
                
        except Exception as e:
            logger.error("pdf_parsing_failed", error=str(e))
            raise ValueError(f"Failed to parse PDF: {str(e)}")
    
    def clean_text(self, text: str) -> str:
        """
        Clean extracted text (remove excessive whitespace, etc.).
        
        Args:
            text: Raw extracted text
            
        Returns:
            Cleaned text
        """
        # Remove excessive newlines
        text = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        
        # Remove multiple spaces
        import re
        text = re.sub(r" +", " ", text)
        
        return text.strip()

