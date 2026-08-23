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
from app.models.product import Product  # noqa: E402


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

        for product in products:
            parsed = parse(product.canonical_name)
            attributes = parsed.specified

            if not attributes:
                unparsed.append(product)
                continue

            before = (product.match_category, product.match_attributes)
            after = (parsed.category, attributes)
            if before == after:
                continue

            print(f"  #{product.id} {product.canonical_name}")
            print(f"      {parsed.category}: {attributes}")

            if not args.dry_run:
                product.match_category = parsed.category
                product.match_attributes = attributes
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
            print(f"\nDRY RUN -- {changed} product(s) would change. Nothing written.")
        else:
            db.commit()
            print(f"\nDone. {changed} product(s) updated.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
