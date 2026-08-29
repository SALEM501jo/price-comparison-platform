"""
Backfill match_category / match_attributes on products created before the
structured matching engine existed.

Safe to re-run: only touches rows that are missing the data, unless --all is
passed (use that after changing the rules in app/matching/rules.py, since the
stored attributes are derived from them).

Usage:
    python scripts/backfill_attributes.py            # fill in the gaps
    python scripts/backfill_attributes.py --all      # recompute everything
    python scripts/backfill_attributes.py --dry-run  # show, change nothing
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Python puts the SCRIPT's directory on sys.path, not the project root, so
# `python scripts/backfill_attributes.py` cannot see the app package without
# this. Keeps the script runnable from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.matching import parse  # noqa: E402
from app.models.alias import ProductAlias  # noqa: E402
from app.models.product import Product  # noqa: E402


def readable_name(db, product: Product) -> str | None:
    """
    Recover a presentable name for a legacy product.

    The old engine stored the NORMALISED name as the display name, so rows read
    "apple iphone 15 256gb 5g blue" in the UI. A store's own listing keeps its
    capitalisation, so borrow that. Returns None when the current name is
    already fine.
    """
    if product.canonical_name != product.canonical_name.lower():
        return None  # already mixed case, leave it alone

    candidates = [
        row.store_product_name
        for row in db.query(ProductAlias.store_product_name).filter(
            ProductAlias.product_id == product.id
        )
        if row.store_product_name and row.store_product_name != row.store_product_name.lower()
    ]
    return max(candidates, key=len) if candidates else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true",
                        help="recompute every product, not just unfilled ones")
    parser.add_argument("--dry-run", action="store_true",
                        help="report what would change without writing")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        query = db.query(Product)
        if not args.all:
            query = query.filter(Product.match_attributes.is_(None))

        products = query.all()
        if not products:
            print("Nothing to backfill.")
            return 0

        print(f"Processing {len(products)} product(s)...\n")

        changed = 0
        unparsed = []

        renamed = 0

        for product in products:
            # WITH THE HINT, because ingest parses with it. Re-deriving
            # without the store's own product_type would give a different
            # answer from the one the scraper reaches, and the backfill
            # would quietly undo the classification it is meant to repair.
            parsed = parse(product.canonical_name, hint=product.category)
            attributes = parsed.specified

            better_name = readable_name(db, product)

            if not attributes:
                unparsed.append(product)
                continue

            before = (product.match_category, product.match_attributes)
            after = (parsed.category, attributes)
            if before == after and not better_name:
                continue

            print(f"  #{product.id} {product.canonical_name}")
            print(f"      {parsed.category}: {attributes}")
            if better_name:
                print(f"      rename -> {better_name!r}")

            if not args.dry_run:
                product.match_category = parsed.category
                product.match_attributes = attributes
                if better_name:
                    product.canonical_name = better_name
            if better_name:
                renamed += 1
            changed += 1

        if unparsed:
            # Not a failure: these fall back to name search. Worth surfacing,
            # because a large count means the rules need a new category.
            print(f"\n  {len(unparsed)} product(s) yielded no attributes:")
            for product in unparsed[:10]:
                print(f"      #{product.id} {product.canonical_name}")
            if len(unparsed) > 10:
                print(f"      ... and {len(unparsed) - 10} more")

        if args.dry_run:
            db.rollback()
            print(f"\nDRY RUN -- {changed} product(s) would change "
                  f"({renamed} rename(s)). Nothing written.")
        else:
            db.commit()
            print(f"\nDone. {changed} product(s) updated, {renamed} renamed.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
