"""
Webhook Notifier Tool

Sends notifications to webhook endpoints.
"""
from typing import Any, Dict, Optional
import httpx
import structlog

from app.tools.base import BaseTool, ToolError
from app.schemas.tool import ToolMetadata, ToolConfigSchema


logger = structlog.get_logger()


class WebhookNotifierTool(BaseTool):
    """
    Tool for sending notifications to webhook endpoints.
    
    Useful for:
    - Trade notifications
    - Alerts and warnings
    - Integration with external systems
    - Custom automation workflows
    """
    
    @classmethod
    def get_metadata(cls) -> ToolMetadata:
        return ToolMetadata(
            tool_type="webhook_notifier",
            name="Webhook Notifier",
            description="Send HTTP notifications to webhook endpoints",
            category="notifier",
            version="1.0.0",
            icon="webhook",
            requires_credentials=False,
            config_schema=ToolConfigSchema(
                type="object",
                title="Webhook Configuration",
                description="Configure webhook endpoint and request settings",
                properties={
                    "url": {
                        "type": "string",
                        "title": "Webhook URL",
                        "description": "Full URL of the webhook endpoint",
                        "default": "https://example.com/webhook"
                    },
                    "method": {
                        "type": "string",
                        "title": "HTTP Method",
                        "enum": ["POST", "PUT", "PATCH"],
                        "default": "POST"
                    },
                    "headers": {
                        "type": "object",
                        "title": "Custom Headers",
                        "description": "Additional HTTP headers (JSON object)",
                        "default": {}
                    },
                    "auth_token": {
                        "type": "string",
                        "title": "Authorization Token",
                        "description": "Bearer token for authentication (optional)"
                    },
                    "timeout": {
                        "type": "number",
                        "title": "Timeout (seconds)",
                        "description": "Request timeout in seconds",
                        "default": 30
                    },
                    "retry_count": {
                        "type": "integer",
                        "title": "Retry Count",
                        "description": "Number of retries on failure",
                        "default": 3
                    }
                },
                required=["url", "method"]
            )
        )
    
    def _validate_config(self):
        """Validate webhook configuration."""
        if not self.config.get("url"):
            raise ValueError("url is required")
        
        method = self.config.get("method", "POST")
        if method not in ["POST", "PUT", "PATCH"]:
            raise ValueError("method must be POST, PUT, or PATCH")
        
        # Validate URL format
        url = self.config["url"]
        if not url.startswith("http://") and not url.startswith("https://"):
            raise ValueError("url must start with http:// or https://")
    
    async def execute(self, payload: Dict[str, Any], **kwargs) -> Dict[str, Any]:
        """
        Send webhook notification.
        
        Args:
            payload: Data to send in the request body
            **kwargs: Additional parameters
            
        Returns:
            Dict with response details
            
        Raises:
            ToolError: If webhook call fails
        """
        url = self.config["url"]
        method = self.config.get("method", "POST")
        timeout = self.config.get("timeout", 30)
        retry_count = self.config.get("retry_count", 3)
        
        # Build headers
        headers = self.config.get("headers", {}).copy()
        headers["Content-Type"] = "application/json"
        
        # Add auth token if provided
        auth_token = self.config.get("auth_token")
        if auth_token:
            headers["Authorization"] = f"Bearer {auth_token}"
        
        logger.info(
            "webhook_request",
            url=url,
            method=method,
            payload_keys=list(payload.keys())
        )
        
        # Attempt request with retries
        for attempt in range(retry_count):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.request(
                        method=method,
                        url=url,
                        json=payload,
                        headers=headers,
                        timeout=timeout
                    )
                    
                    response.raise_for_status()
                    
                    logger.info(
                        "webhook_success",
                        url=url,
                        status_code=response.status_code,
                        attempt=attempt + 1
                    )
                    
                    return {
                        "success": True,
                        "status_code": response.status_code,
                        "response": response.json() if response.content else {},
                        "attempt": attempt + 1
                    }
                    
            except httpx.HTTPStatusError as e:
                logger.error(
                    "webhook_http_error",
                    url=url,
                    status_code=e.response.status_code,
                    attempt=attempt + 1,
                    error=str(e)
                )
                if attempt == retry_count - 1:
                    raise ToolError(f"Webhook failed after {retry_count} attempts: {e}")
                
            except Exception as e:
                logger.error(
                    "webhook_error",
                    url=url,
                    attempt=attempt + 1,
                    error=str(e),
                    exc_info=True
                )
                if attempt == retry_count - 1:
                    raise ToolError(f"Webhook failed after {retry_count} attempts: {e}")
        
        raise ToolError(f"Webhook failed after {retry_count} attempts")

