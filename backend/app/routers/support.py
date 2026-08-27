"""
The contact form.

Open to anyone, signed in or not, because the people who most need it are the
ones who cannot get in. That makes it an unauthenticated endpoint that sends
mail, so it is rate limited hard and the message is stored regardless of
whether the notification goes out.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.dependencies import get_current_user_optional
from app.logging_config import get_security_logger, pseudonymize
from app.models.support import SupportMessage
from app.models.user import User
from app.security.rate_limiter import strict_rate_limit
from app.services import email as email_service
from app.services.email import Message

router = APIRouter()
logger = get_security_logger("app.support")
settings = get_settings()


class SupportRequest(BaseModel):
    # Asked for even when signed in: someone locked out writes from whatever
    # address they can reach, which may not be the one on the account.
    email: EmailStr
    subject: Optional[str] = Field(None, max_length=150)
    body: str = Field(..., min_length=10, max_length=4000)

    @field_validator("subject", "body")
    @classmethod
    def tidy(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = " ".join(v.split())
        return v or None


@router.post("/contact", status_code=status.HTTP_202_ACCEPTED)
async def contact(
    request: Request,
    body: SupportRequest,
    db: Session = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """
    Receive a support message.

    THE ROW IS THE RECORD, the email is a notification about it. Storing first
    means a message survives an SMTP outage, a console backend in development,
    and a typo in the support address -- none of which the person writing in
    can see or do anything about.

    Always 202, and never reveals whether the address belongs to an account:
    this endpoint would otherwise be a membership oracle exactly like
    /auth/forgot-password.
    """
    await strict_rate_limit(request)

    record = SupportMessage(
        email=body.email,
        subject=body.subject,
        body=body.body,
        user_id=current_user.id if current_user else None,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    logger.info(
        "Support message received",
        extra={
            "action": "support_message",
            "target": pseudonymize(body.email),
            "user_id": current_user.id if current_user else None,
            "success": True,
        },
    )

    # Best effort. send() never raises, and a failure here must not lose the
    # message or tell the sender their problem was not received.
    if settings.support_email:
        email_service.send(
            Message(
                to=settings.support_email,
                subject=f"[Ahsan Se3r] {body.subject or 'Support request'}",
                text=(
                    f"From: {body.email}\n"
                    f"Account: {current_user.email if current_user else 'not signed in'}\n"
                    f"Message #{record.id}\n\n"
                    f"{body.body}\n"
                ),
            )
        )

    return {"status": "received", "id": record.id}
