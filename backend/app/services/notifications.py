"""
Price alert notifications.

Until now alerts were only evaluated when a user happened to open the page,
which makes "tell me when it drops" a promise the system never kept. This runs
after each scrape and actually tells them.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.price import PriceAlert
from app.models.product import Product
from app.models.user import User
from app.services import email as email_service
from app.services.email import Message
from app.services.search import price_summary

logger = logging.getLogger("app.notifications")
settings = get_settings()


def _product_link(product_id: int) -> str:
    return f"{settings.app_base_url.rstrip('/')}/product/{product_id}"


def _message(user: User, product: Product, target, current, store: str | None) -> Message:
    link = _product_link(product.id)
    where = f" at {store}" if store else ""
    return Message(
        to=user.email,
        subject=f"Price drop: {product.canonical_name}",
        text=(
            f"{product.canonical_name} has reached your target price.\n\n"
            f"  Your target: {target} JOD\n"
            f"  Now:         {current} JOD{where}\n\n"
            f"{link}\n\n"
            "Prices include delivery. You are getting this because you set an "
            "alert on this product; delete it in the app to stop.\n"
        ),
        html=(
            f"<p><strong>{product.canonical_name}</strong> has reached your "
            "target price.</p>"
            f"<p>Your target: {target} JOD<br>Now: <strong>{current} JOD</strong>"
            f"{where}</p>"
            f'<p><a href="{link}">View the comparison</a></p>'
            "<p>Prices include delivery. You are getting this because you set "
            "an alert on this product; delete it in the app to stop.</p>"
        ),
    )


def process_alerts(db: Session) -> dict:
    """
    Notify on every alert whose target is now met, and reset those that are not.

    Returns counts, so a scrape run can report what it did.
    """
    rows = (
        db.query(PriceAlert, Product, User)
        .join(Product, PriceAlert.product_id == Product.id)
        .join(User, PriceAlert.user_id == User.id)
        .filter(PriceAlert.is_active.is_(True))
        .all()
    )
    if not rows:
        return {"checked": 0, "notified": 0, "reset": 0, "skipped_unverified": 0}

    prices = price_summary(db, (product.id for _, product, _ in rows))

    notified = 0
    reset = 0
    skipped_unverified = 0

    for alert, product, user in rows:
        current = prices.get(product.id, {}).get("best_total")

        if current is None or current > alert.target_price:
            # Back above target: clear the marker so a future drop notifies
            # again rather than being suppressed forever by one old send.
            if alert.notified_at is not None:
                alert.notified_at = None
                reset += 1
            continue

        if alert.notified_at is not None:
            continue  # already told them, and the price has not recovered since

        if user.email_verified_at is None:
            # Never send to an unconfirmed address. Anyone can type a stranger's
            # email at signup, and an unverified account is exactly how this
            # feature would be turned into a way to mail them.
            skipped_unverified += 1
            continue

        store = prices.get(product.id, {}).get("best")
        if email_service.send(_message(user, product, alert.target_price, current, store)):
            alert.notified_at = datetime.now(timezone.utc)
            notified += 1
            logger.info(
                "Price alert notified",
                extra={
                    "user_id": user.id,
                    "action": "alert_notify",
                    "target": product.canonical_name,
                    "success": True,
                },
            )

    db.commit()

    result = {
        "checked": len(rows),
        "notified": notified,
        "reset": reset,
        "skipped_unverified": skipped_unverified,
    }
    logger.info(
        "Alerts processed",
        extra={"action": "alerts_processed", "target": str(result), "success": True},
    )
    return result


if __name__ == "__main__":
    from app.database import SessionLocal
    from app.logging_config import setup_logging

    setup_logging()
    db = SessionLocal()
    try:
        print(process_alerts(db))
    finally:
        db.close()
