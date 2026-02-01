"""
FastAPI HTTP API for Signal Generator Monitoring

Provides HTTP endpoints for monitoring signal generation.
"""
from fastapi import FastAPI, HTTPException
from typing import List, Dict, Any
import structlog

logger = structlog.get_logger()

# Global reference to the service (will be set by main)
_service_instance = None


def set_service_instance(service):
    """Set the global service instance for API access."""
    global _service_instance
    _service_instance = service


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Signal Generator API",
        description="HTTP API for monitoring signal generation",
        version="1.0.0"
    )
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "signal-generator",
            "running": _service_instance.running if _service_instance else False
        }
    
    @app.get("/recent-signals", response_model=List[Dict[str, Any]])
    async def get_recent_signals(limit: int = 50):
        """
        Get recent signals for monitoring.
        
        Args:
            limit: Maximum number of signals to return (default: 50, max: 100)
            
        Returns:
            List of recent signal objects
        """
        if not _service_instance:
            raise HTTPException(status_code=503, detail="Service not initialized")
        
        # Cap limit at 100
        limit = min(limit, 100)
        
        try:
            signals = _service_instance.get_recent_signals(limit=limit)
            return signals
        except Exception as e:
            logger.error("failed_to_fetch_recent_signals", error=str(e))
            raise HTTPException(status_code=500, detail=f"Failed to fetch signals: {str(e)}")
    
    return app


# Create the app instance
app = create_app()
