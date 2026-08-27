"""
One shopper reaching out to one shop.

WHY THIS TABLE EXISTS: there is no checkout here. A shopper who decides to buy
taps Call or WhatsApp and the rest happens on the phone, which means the
platform's entire contribution to a shop is invisible to it. A merchant asked
to pay 10 JOD a month will reasonably ask "how many customers did you send
me?", and until now the honest answer was that nobody knew.

WHAT IS AND IS NOT MEASURED -- and the wording matters everywhere this is
shown:

    This counts TAPS, not calls, and certainly not sales.

A tap is a shopper asking for the number. Whether they rang it, whether it was
answered, and whether anyone bought anything are all outside what a web page
can observe. Reporting taps as "calls" would inflate a number a merchant is
being asked to pay against, which is the one number that has to be beyond
argument. The UI says "taps" for that reason.

PRIVACY: no IP address, no user id, no session identifier. A row is
(which shop, which product, which channel, when) and nothing else, so this
cannot be turned into a record of what any individual browsed. That is a
deliberate limit rather than an oversight -- Jordan's Personal Data Protection
Law No. 24 of 2023 covers exactly this kind of behavioural data, and the
analytics a shop actually needs are counts, which do not require identifying
anybody.

The cost of that choice is that de-duplication is impossible: one shopper
tapping twice is two taps. Counting unique people would mean identifying
people. Taps is the honest unit, so taps is what is reported.
"""

import enum

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.sql import func

from app.database import Base


class ContactChannel(str, enum.Enum):
    """How the shopper chose to reach the shop."""

    call = "call"
    whatsapp = "whatsapp"
    facebook = "facebook"


# Stored as text, not a database enum: the project's standing decision, because
# adding a value to a PostgreSQL enum needs ALTER TYPE and cannot be reversed
# without rewriting the column. See ProductAlias.condition and ScrapeJob.status.
CONTACT_CHANNELS: tuple[str, ...] = tuple(c.value for c in ContactChannel)


class ContactEvent(Base):
    __tablename__ = "contact_events"

    id = Column(Integer, primary_key=True, index=True)

    # CASCADE: a deleted store's tap history is meaningless and should not
    # outlive it.
    store_id = Column(
        Integer,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # SET NULL rather than CASCADE: the shop was still contacted even if the
    # product row is later merged away or cleaned up, and losing the tap would
    # quietly reduce a number the merchant is billed against.
    product_id = Column(
        Integer, ForeignKey("products.id", ondelete="SET NULL"), index=True
    )

    channel = Column(String(16), nullable=False, index=True)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (
        # Every question asked of this table is "this shop, over this period",
        # from both the merchant dashboard and the admin screen. The composite
        # index serves that directly; the single-column indexes above do not,
        # because the store filter alone still leaves every row that shop has
        # ever collected.
        Index("ix_contact_events_store_created", "store_id", "created_at"),
    )
