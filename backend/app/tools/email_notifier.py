"""
Email Notifier Tool

Sends email notifications via AWS SES or SMTP.
"""
from typing import Any, Dict, Optional, List
import structlog

from app.tools.base import BaseTool, ToolError
from app.schemas.tool import ToolMetadata, ToolConfigSchema
from app.config import settings


logger = structlog.get_logger()


class EmailNotifierTool(BaseTool):
    """
    Tool for sending email notifications.
    
    Supports:
    - AWS SES (default)
    - SMTP (custom server)
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            tool_type="email_notifier",
            name="Email Notifier",
            description="Send email notifications via AWS SES or SMTP",
            category="notifier",
            version="1.0.0",
            icon="email",
            requires_credentials=True,
            config_schema=ToolConfigSchema(
                type="object",
                title="Email Notifier Configuration",
                description="Configure email sending settings",
                properties={
                    "provider": {
                        "type": "string",
                        "title": "Email Provider",
                        "enum": ["ses", "smtp"],
                        "default": "ses"
                    },
                    "from_email": {
                        "type": "string",
                        "title": "From Email",
                        "description": "Sender email address"
                    },
                    "to_emails": {
                        "type": "array",
                        "title": "To Emails",
                        "description": "Recipient email addresses (comma-separated)"
                    },
                    "subject_prefix": {
                        "type": "string",
                        "title": "Subject Prefix",
                        "description": "Prefix added to all email subjects",
                        "default": "[Trading Bot]"
                    },
                    "use_env_config": {
                        "type": "boolean",
                        "title": "Use Environment Config",
                        "description": "Use AWS SES settings from environment",
                        "default": True
                    },
                    "smtp_server": {
                        "type": "string",
                        "title": "SMTP Server",
                        "description": "SMTP server hostname (if using SMTP)"
                    },
                    "smtp_port": {
                        "type": "integer",
                        "title": "SMTP Port",
                        "description": "SMTP server port",
                        "default": 587
                    },
                    "smtp_username": {
                        "type": "string",
                        "title": "SMTP Username",
                        "description": "SMTP authentication username"
                    },
                    "smtp_password": {
                        "type": "string",
                        "title": "SMTP Password",
                        "description": "SMTP authentication password"
                    }
                },
                required=["provider", "from_email", "to_emails"]
            )
        )
    
    def _validate_config(self):
        """Validate email configuration."""
        provider = self.config.get("provider", "ses")
        if provider not in ["ses", "smtp"]:
            raise ValueError("provider must be 'ses' or 'smtp'")
        
        if not self.config.get("from_email"):
            raise ValueError("from_email is required")
        
        if not self.config.get("to_emails"):
            raise ValueError("to_emails is required")
        
        if provider == "smtp":
            if not self.config.get("smtp_server"):
                raise ValueError("smtp_server required when using SMTP provider")
    
    async def execute(
        self,
        subject: str,
        body: str,
        html: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Send an email notification.
        
        Args:
            subject: Email subject
            body: Email body (text or HTML)
            html: Whether body is HTML (default: False)
            **kwargs: Additional parameters
            
        Returns:
            Dict with send status
            
        Raises:
            ToolError: If email sending fails
        """
        provider = self.config.get("provider", "ses")
        from_email = self.config["from_email"]
        to_emails = self.config["to_emails"]
        subject_prefix = self.config.get("subject_prefix", "[Trading Bot]")
        
        full_subject = f"{subject_prefix} {subject}"
        
        logger.info(
            "email_send_request",
            provider=provider,
            from_email=from_email,
            to_emails=to_emails,
            subject=full_subject
        )
        
        try:
            if provider == "ses":
                return await self._send_via_ses(from_email, to_emails, full_subject, body, html)
            else:
                return await self._send_via_smtp(from_email, to_emails, full_subject, body, html)
                
        except Exception as e:
            logger.error("email_send_failed", error=str(e), exc_info=True)
            raise ToolError(f"Email sending failed: {e}")
    
    async def _send_via_ses(
        self,
        from_email: str,
        to_emails: List[str],
        subject: str,
        body: str,
        html: bool
    ) -> Dict[str, Any]:
        """Send email via AWS SES."""
        # Mock SES sending for now
        # In production, use boto3:
        # import boto3
        # ses_client = boto3.client('ses', region_name=settings.AWS_REGION)
        # response = ses_client.send_email(...)
        
        logger.info("ses_email_sent", to_emails=to_emails, subject=subject)
        
        return {
            "success": True,
            "provider": "ses",
            "message_id": "mock_ses_message_123",
            "from": from_email,
            "to": to_emails,
            "subject": subject
        }
    
    async def _send_via_smtp(
        self,
        from_email: str,
        to_emails: List[str],
        subject: str,
        body: str,
        html: bool
    ) -> Dict[str, Any]:
        """Send email via SMTP."""
        # Mock SMTP sending for now
        # In production, use aiosmtplib:
        # import aiosmtplib
        # from email.message import EmailMessage
        
        logger.info("smtp_email_sent", to_emails=to_emails, subject=subject)
        
        return {
            "success": True,
            "provider": "smtp",
            "from": from_email,
            "to": to_emails,
            "subject": subject
        }

