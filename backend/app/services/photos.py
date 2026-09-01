"""
Storing and finding merchant photos.

THE SEAM. This is the only module that reads or writes photo bytes. Everything
else asks it for a photo or hands it one. That is what makes the storage
decision reversible: moving these bytes to object storage later is a rewrite
of this file, not of every caller -- see the note on ListingPhoto for why
Postgres is the right answer at this size.

A PHOTO OBEYS THE SAME VISIBILITY RULE AS A PRICE. An unverified merchant's
photo is not served to shoppers, for the reason `Store.visible_to_shoppers`
already gives: until an admin has checked the claim, nothing connects the name
on the listing to the shop it names, and an unchecked shop's image on a
product page is a stronger endorsement than its price. Filtering in the QUERY
rather than at the template, for the same reason the prices do.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.alias import ProductAlias
from app.models.listing_photo import ListingPhoto
from app.models.store import Store
from app.services.images import ProcessedImage


def save_photo(db: Session, alias_id: int, processed: ProcessedImage) -> ListingPhoto:
    """
    Attach a processed photo to a listing, replacing any it already has.

    Replace rather than accumulate: a shop owner re-uploading has corrected a
    bad shot, not added a second angle. The unique constraint on alias_id
    enforces it at the database; this is the path that makes it a normal
    action instead of an error.
    """
    existing = (
        db.query(ListingPhoto).filter(ListingPhoto.alias_id == alias_id).one_or_none()
    )
    if existing is None:
        existing = ListingPhoto(alias_id=alias_id)
        db.add(existing)

    existing.content_type = processed.content_type
    existing.data = processed.data
    existing.width = processed.width
    existing.height = processed.height
    existing.byte_size = processed.byte_size
    existing.checksum = processed.checksum
    return existing


def delete_photo(db: Session, alias_id: int) -> bool:
    """Remove a listing's photo. True if there was one."""
    removed = (
        db.query(ListingPhoto).filter(ListingPhoto.alias_id == alias_id).delete()
    )
    return bool(removed)


def photo_for_listing(db: Session, alias_id: int) -> ListingPhoto | None:
    """One listing's photo, with no visibility filtering.

    For the merchant's own dashboard: a shop must be able to see the photo it
    uploaded while its claim is still pending, or it cannot tell whether the
    upload worked.
    """
    return (
        db.query(ListingPhoto).filter(ListingPhoto.alias_id == alias_id).one_or_none()
    )


def photo_for_product(db: Session, product_id: int) -> ListingPhoto | None:
    """
    The photo to show for a product, from any shop a shopper may see.

    Oldest first, deliberately. The rule has to be DETERMINISTIC or the
    product's picture changes every time a query happens to order differently,
    and it has to not reward re-uploading, or "whose photo is on the product"
    becomes something merchants compete over by spamming. First to supply one
    keeps it until they remove it.
    """
    return (
        db.query(ListingPhoto)
        .join(ProductAlias, ProductAlias.id == ListingPhoto.alias_id)
        .join(Store, Store.id == ProductAlias.store_id)
        .filter(ProductAlias.product_id == product_id)
        .filter(Store.visible_to_shoppers())
        .order_by(ListingPhoto.uploaded_at.asc(), ListingPhoto.id.asc())
        .first()
    )


def product_ids_with_photos(db: Session, product_ids: list[int]) -> set[int]:
    """
    Which of these products have a merchant photo a shopper may see.

    ONE QUERY FOR THE WHOLE PAGE. A search result carries up to twenty
    products per tier, and asking per product would put sixty round trips
    behind one search to answer a question that is a single join. The bytes
    are never loaded -- only the product ids -- which is the other reason the
    photos live in their own table.
    """
    if not product_ids:
        return set()

    rows = db.execute(
        select(ProductAlias.product_id)
        .join(ListingPhoto, ListingPhoto.alias_id == ProductAlias.id)
        .join(Store, Store.id == ProductAlias.store_id)
        .where(ProductAlias.product_id.in_(product_ids))
        .where(Store.visible_to_shoppers())
        .distinct()
    ).scalars()
    return set(rows)


def photo_path(product_id: int) -> str:
    """Where a product's merchant photo is served from."""
    return f"/products/{product_id}/photo"


def display_image_url(
    product_id: int, scraped_url: str | None, has_merchant_photo: bool
) -> str | None:
    """
    The one image URL a client should render for a product.

    SCRAPED WINS. A retailer's own product shot is a press image of the model,
    which is what a shopper browsing a list wants; a merchant photo is of one
    specific unit, and is most useful where it cannot be mistaken for the
    other -- next to that shop's offer. Preferring the merchant photo on the
    card would also mean a single shop could change the picture on a product
    that four other shops sell.

    Returns null when there is neither, so the client can draw a placeholder
    rather than a broken image. Resolving one field here rather than sending
    two and letting each client decide is what stops the search page and the
    product page disagreeing about which picture a product has.
    """
    if scraped_url:
        return scraped_url
    if has_merchant_photo:
        return photo_path(product_id)
    return None
