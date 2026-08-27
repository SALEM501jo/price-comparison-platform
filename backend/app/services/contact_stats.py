"""
Counting contact taps, and the one honest way to describe them.

Shared by the merchant dashboard and the admin screen so both report the same
numbers from the same query. Two implementations would drift, and a merchant
seeing a different figure from the one the admin is looking at while they are
on the phone to each other is a support problem nobody needs.

READ THE MODEL DOCSTRING for what a tap is and is not. In short: a tap is a
shopper asking for the number. It is not a call, and it is certainly not a
sale. Every label this module feeds says "taps".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.contact_event import CONTACT_CHANNELS, ContactEvent

# The reporting window. Thirty days because that is the period a monthly fee
# is charged over, so the number a shop is shown is the number it is being
# asked to pay against.
DEFAULT_WINDOW_DAYS = 30


def _cutoff(days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def totals_for_store(
    db: Session, store_id: int, days: int = DEFAULT_WINDOW_DAYS
) -> dict:
    """
    One shop's taps, by channel, over the window.

    Every channel is present in the result even when its count is zero. A
    dashboard that hides empty channels makes "nobody has used WhatsApp" look
    identical to "WhatsApp is not set up", and those need different actions
    from the shop owner.
    """
    rows = (
        db.query(ContactEvent.channel, func.count(ContactEvent.id))
        .filter(ContactEvent.store_id == store_id)
        .filter(ContactEvent.created_at >= _cutoff(days))
        .group_by(ContactEvent.channel)
        .all()
    )
    by_channel = {channel: 0 for channel in CONTACT_CHANNELS}
    for channel, count in rows:
        by_channel[channel] = count

    return {
        "window_days": days,
        "total": sum(by_channel.values()),
        "by_channel": by_channel,
    }


def totals_for_stores(
    db: Session, store_ids: list[int], days: int = DEFAULT_WINDOW_DAYS
) -> dict[int, dict]:
    """
    The same figures for many shops, in ONE query.

    The admin screen lists every store; a per-row call here would be the same
    N+1 shape this codebase has already removed from price_summary() and the
    store listing page.
    """
    if not store_ids:
        return {}

    rows = (
        db.query(
            ContactEvent.store_id,
            ContactEvent.channel,
            func.count(ContactEvent.id),
        )
        .filter(ContactEvent.store_id.in_(store_ids))
        .filter(ContactEvent.created_at >= _cutoff(days))
        .group_by(ContactEvent.store_id, ContactEvent.channel)
        .all()
    )

    summary: dict[int, dict] = {
        store_id: {
            "window_days": days,
            "total": 0,
            "by_channel": {channel: 0 for channel in CONTACT_CHANNELS},
        }
        for store_id in store_ids
    }
    for store_id, channel, count in rows:
        bucket = summary[store_id]
        bucket["by_channel"][channel] = count
        bucket["total"] += count

    return summary


def per_product_for_store(
    db: Session, store_id: int, days: int = DEFAULT_WINDOW_DAYS, limit: int = 10
) -> list[dict]:
    """
    Which products people are ringing about, busiest first.

    The actionable half of the dashboard: a total tells a shop the platform is
    working, this tells it what to stock and what to reprice.
    """
    from app.models.product import Product

    rows = (
        db.query(
            Product.id,
            Product.canonical_name,
            func.count(ContactEvent.id).label("taps"),
        )
        .join(ContactEvent, ContactEvent.product_id == Product.id)
        .filter(ContactEvent.store_id == store_id)
        .filter(ContactEvent.created_at >= _cutoff(days))
        .group_by(Product.id, Product.canonical_name)
        .order_by(func.count(ContactEvent.id).desc(), Product.id)
        .limit(limit)
        .all()
    )
    return [
        {"product_id": pid, "product_name": name, "taps": taps}
        for pid, name, taps in rows
    ]
