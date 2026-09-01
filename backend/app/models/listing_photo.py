"""
A photo a merchant took of the unit they are actually selling.

WHY THIS IS ITS OWN TABLE, AND ON THE ALIAS:

`Product.image_url` is a scraped URL on the SHARED product row -- one image
for a model, hotlinked from whichever shop's CDN supplied it first. That is
right for scraped stock, where any shop's press photo of an iPhone 16 is as
good as another's.

It is wrong for merchants twice over. Two shops selling the same handset would
compete for one column, and first-writer-wins stops being a tiebreak and
becomes a land grab. More importantly, a merchant photo is evidence about ONE
UNIT: this project already requires a second-hand listing to disclose battery
health and damage, and the photograph of the actual scratch is the same kind
of claim. That belongs on the alias, next to the other facts about the unit,
for exactly the reason alias.py already gives.

WHY THE BYTES ARE IN POSTGRES rather than object storage: the same reasoning
that put the scrape queue in a table instead of adding a broker. Object
storage means a second service, a second set of credentials, a bucket policy
and a CORS rule, to solve a problem that at this size is a few hundred rows.
A re-encoded photo is 100-200KB, so a free 0.5GB database holds several
thousand -- far past the point where this platform would have other reasons to
change. `photos.py` is the seam: it is the only module that reads or writes
these bytes, so moving them to R2 later is one file, not a migration of every
caller.

WHY IT IS A SEPARATE TABLE rather than a column on ProductAlias: every search
query touches product_aliases, and a bytea column on a hot table gets dragged
into result sets by any `SELECT *` that forgets to defer it. Keeping the bytes
one join away means the row you never asked for costs nothing.
"""

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    func,
)
from sqlalchemy.orm import relationship

from app.database import Base


class ListingPhoto(Base):
    __tablename__ = "listing_photos"

    id = Column(Integer, primary_key=True, index=True)

    # UNIQUE: one photo per listing. Re-uploading replaces rather than
    # accumulates, which is what a shop owner correcting a bad shot means. The
    # table shape allows a second photo later; the constraint is what stops it
    # happening by accident today.
    alias_id = Column(
        Integer,
        ForeignKey("product_aliases.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Always image/webp today -- everything is re-encoded. Stored rather than
    # assumed so that the serving layer reads what it sends, and so a future
    # format change does not silently mislabel every row written before it.
    content_type = Column(String(32), nullable=False)

    data = Column(LargeBinary, nullable=False)

    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)
    byte_size = Column(Integer, nullable=False)

    # SHA-256 of the stored bytes, served as the ETag. Serving images out of
    # the database means every uncached request is a query; a strong validator
    # turns a repeat view into a 304 with no body, which is the difference
    # between the database serving a page of thumbnails once and serving it
    # on every scroll.
    checksum = Column(String(64), nullable=False, index=True)

    uploaded_at = Column(DateTime(timezone=True), server_default=func.now())

    alias = relationship("ProductAlias", back_populates="photo")
