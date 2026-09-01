"""
Admin routes for contact-form messages.

The contact form has always STORED its messages -- the row is the
record and the email is only a notification about it -- but for a long
time nothing read them back. In development the console mail backend
discards the notification and SUPPORT_EMAIL is optional in production,
so a support request went into the database and was never seen by a
human. That is worse than having no contact form, because the person
who wrote in is waiting.
"""


from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.logging_config import get_security_logger
from app.models.support import SupportMessage
from app.models.user import User

router = APIRouter()
logger = get_security_logger("app.admin")


# --- Support messages -------------------------------------------------------
#
# The contact form has always STORED its messages -- the row is the record and
# the email is only a notification about it -- but nothing ever read them back.
# In development EMAIL_BACKEND=console throws the notification away, and
# SUPPORT_EMAIL is optional in production, so for anyone without SMTP wired up
# a support request went into the database and was never seen by a human. That
# is worse than not having a contact form, because the person who wrote in is
# waiting for an answer.


@router.get("/support-messages")
async def list_support_messages(
    handled: bool | None = Query(
        None, description="Filter by handled state; omit for everything"
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Messages sent through the contact form, newest first."""
    query = db.query(SupportMessage)
    if handled is not None:
        query = query.filter(SupportMessage.handled.is_(handled))

    rows = (
        query.order_by(SupportMessage.created_at.desc(), SupportMessage.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # The sender's account, when they had one. Resolved in one lookup rather
    # than per row -- the same N+1 shape removed from the store listing above.
    user_ids = [row.user_id for row in rows if row.user_id]
    users = {
        user.id: user.email
        for user in db.query(User).filter(User.id.in_(user_ids or [0])).all()
    }

    unhandled = (
        db.query(func.count(SupportMessage.id))
        .filter(SupportMessage.handled.is_(False))
        .scalar()
    )

    return {
        "unhandled": unhandled,
        "messages": [
            {
                "id": row.id,
                # The address to REPLY to, which is deliberately not the same
                # as the account: someone locked out writes from whatever
                # address they can still reach.
                "email": row.email,
                "subject": row.subject,
                "body": row.body,
                "created_at": row.created_at,
                "handled": row.handled,
                "account_email": users.get(row.user_id),
            }
            for row in rows
        ],
    }


@router.post("/support-messages/{message_id}/handled")
async def set_support_message_handled(
    message_id: int,
    handled: bool = True,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Mark a message dealt with, or put it back.

    Reversible on purpose: "handled" is a note to the next admin, not an
    archive, and marking the wrong row should not lose it.
    """
    message = (
        db.query(SupportMessage).filter(SupportMessage.id == message_id).first()
    )
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")

    message.handled = handled
    db.commit()

    logger.info("Admin updated a support message", extra={
        "admin_id": admin.id,
        "action": "admin_support_handled",
        "target": f"message {message.id} -> handled={handled}",
    })
    return {"id": message.id, "handled": message.handled}
