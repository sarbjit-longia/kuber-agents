"""
Public SMS Consent API endpoint.

No authentication required — this is the URL submitted to Twilio
for toll-free verification as proof of opt-in.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
import structlog

from app.database import get_db
from app.models.sms_consent_log import SmsConsentLog
from app.schemas.user import SmsConsentPublicRequest

logger = structlog.get_logger()

router = APIRouter(prefix="/sms-consent", tags=["sms-consent"])


@router.post("/public")
async def submit_public_consent(
    body: SmsConsentPublicRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Record SMS opt-in consent from the public consent form.

    This endpoint requires no authentication. It is the URL provided
    to Twilio as proof of user opt-in for toll-free verification.
    Only consent=True is accepted (opt-in); revocation is done via
    the authenticated settings endpoint or by replying STOP.
    """
    if not body.consent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Consent must be true to opt in. To revoke consent, reply STOP to any SMS or use your account settings.",
        )

    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent", "")[:500]

    log_entry = SmsConsentLog(
        phone_number=body.phone_number,
        user_id=None,
        consent_given=True,
        consent_method="public_form",
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(log_entry)
    await db.commit()

    logger.info(
        "sms_consent_public_recorded",
        phone=body.phone_number[:6] + "****",
        ip=ip_address,
    )

    return {
        "status": "recorded",
        "message": "Your consent has been recorded. You may now receive SMS trade approval notifications from CloverCharts.",
    }
