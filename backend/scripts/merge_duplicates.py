"""
Merge canonical products that describe the same physical item.

WHY THIS EXISTS: the original matching engine split one product across several
canonical rows -- "apple iphone 15 128gb 5g black", "... 5g midnight" and
"... black" were three products for one phone. The fix to the engine stops NEW
duplicates appearing; it does nothing about the ones already stored. Their
user-visible symptom is a fragmented price comparison: the same handset listed
three times showing 2, 1 and 1 stores instead of once showing 4.

Grouping key is (match_category, match_attributes) -- products the matching
engine considers identical. Run backfill_attributes.py first.

Usage:
    python scripts/merge_duplicates.py --dry-run   # show what would merge
    python scripts/merge_duplicates.py             # do it
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.models.alias import ProductAlias  # noqa: E402
from app.models.price import PriceAlert, WishlistItem  # noqa: E402
from app.models.product import Product  # noqa: E402


def attribute_key(product: Product):
    """Products are the same item when the engine extracts the same attributes."""
    attributes = product.match_attributes or {}
    if not attributes:
        return None  # unparsed -- never merge on an empty key
    return (product.match_category, tuple(sorted(attributes.items())))


def best_name(db, group: list[Product]) -> str:
    """
    Choose the most presentable name for the survivor.

    Legacy rows stored a normalised name ("apple iphone 15 128gb 5g black")
    because the old code used the comparison form as the display form. A store's
    own listing keeps its capitalisation, so prefer that when available.
    """
    aliases = (
        db.query(ProductAlias.store_product_name)
        .filter(ProductAlias.product_id.in_([p.id for p in group]))
        .all()
    )
    candidates = [a.store_product_name for a in aliases if a.store_product_name]
    mixed_case = [c for c in candidates if c != c.lower()]
    if mixed_case:
        return max(mixed_case, key=len)
    return max((p.canonical_name for p in group), key=len)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        groups: dict[tuple, list[Product]] = defaultdict(list)
        for product in db.query(Product).order_by(Product.id).all():
            key = attribute_key(product)
            if key is not None:
                groups[key].append(product)

        duplicates = {k: v for k, v in groups.items() if len(v) > 1}
        if not duplicates:
            print("No duplicate products found.")
            return 0

        merged = 0
        removed = 0

        for group in duplicates.values():
            # Oldest row survives: it owns the most inbound references and its
            # id may already be shared in links or bookmarks.
            survivor, losers = group[0], group[1:]
            name = best_name(db, group)

            print(f"\nMerging into #{survivor.id}: {name!r}")
            for loser in losers:
                alias_count = (
                    db.query(ProductAlias).filter_by(product_id=loser.id).count()
                )
                print(f"    absorbing #{loser.id} {loser.canonical_name!r} "
                      f"({alias_count} alias(es))")

            if args.dry_run:
                merged += 1
                removed += len(losers)
                continue

            loser_ids = [p.id for p in losers]

            # Aliases carry the store listings and their prices; repointing
            # them is what actually consolidates the comparison.
            db.query(ProductAlias).filter(
                ProductAlias.product_id.in_(loser_ids)
            ).update({ProductAlias.product_id: survivor.id}, synchronize_session=False)

            # Wishlists have a unique (user_id, product_id): a user holding both
            # the survivor and a loser would collide on repoint, so drop the
            # redundant row instead.
            already = {
                row.user_id
                for row in db.query(WishlistItem.user_id).filter_by(
                    product_id=survivor.id
                )
            }
            for item in db.query(WishlistItem).filter(
                WishlistItem.product_id.in_(loser_ids)
            ):
                if item.user_id in already:
                    db.delete(item)
                else:
                    item.product_id = survivor.id
                    already.add(item.user_id)

            db.query(PriceAlert).filter(PriceAlert.product_id.in_(loser_ids)).update(
                {PriceAlert.product_id: survivor.id}, synchronize_session=False
            )

            survivor.canonical_name = name
            for loser in losers:
                db.delete(loser)

            merged += 1
            removed += len(losers)

        if args.dry_run:
            db.rollback()
            print(f"\nDRY RUN -- would merge {merged} group(s), "
                  f"removing {removed} duplicate product(s). Nothing written.")
        else:
            db.commit()
            print(f"\nDone. Merged {merged} group(s), "
                  f"removed {removed} duplicate product(s).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
