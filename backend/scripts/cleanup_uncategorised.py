"""
Remove catalogue rows the matching engine cannot categorise.

WHY THIS EXISTS
Two earlier ingest runs used looser rules than the ones now in rules.py:

  * the scraper's relevance gate called detect_category(), which only asks
    whether a category word appears, while the storage side called parse(),
    which also enforces requires_any. Everything between the two gates was
    ingested and then filed with no category -- printers, mice, backpacks.

  * the brand-adjacent model rule accepted a bare number next to a brand, so
    televisions, microwaves and earbuds were stored as phones.

Both are fixed. This clears what the old rules let through. Nothing here
changes behaviour -- it only deletes rows that today's parser rejects, which
are invisible to search either way.

SAFETY, verified before writing this:
  * no wishlist item and no price alert points at any affected row
  * all three mock-store products (DNA / Carrefour / City Center) survive
  * aliases, prices and price history cascade from products by FK

Run with --apply to actually delete. Without it, this only reports.

    cd backend
    .venv/Scripts/python.exe <path-to-this-file>            # dry run
    .venv/Scripts/python.exe <path-to-this-file> --apply    # delete
"""

import sys

sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.matching import parse  # noqa: E402

PROTECTED_STORES = ("DNA Jordan", "Carrefour Jordan", "City Center")


def main() -> int:
    apply = "--apply" in sys.argv
    db = SessionLocal()
    try:
        rows = db.execute(
            text("select id, canonical_name, match_category from products")
        ).fetchall()
        doomed = [r for r in rows if parse(r[1]).category is None]
        doomed_ids = [r[0] for r in doomed]

        if not doomed_ids:
            print("Nothing to delete -- every product parses to a category.")
            return 0

        wishlisted = {
            x[0] for x in db.execute(text("select distinct product_id from wishlist_items"))
        }
        alerted = {
            x[0] for x in db.execute(text("select distinct product_id from price_alerts"))
        }
        protected = {
            x[0]
            for x in db.execute(
                text(
                    "select distinct p.id from products p "
                    "join product_aliases a on a.product_id = p.id "
                    "join stores s on s.id = a.store_id "
                    "where s.name = any(:names)"
                ),
                {"names": list(PROTECTED_STORES)},
            )
        }

        collisions = set(doomed_ids) & (wishlisted | alerted | protected)
        if collisions:
            print(f"REFUSING: {len(collisions)} row(s) are referenced by user data")
            for pid in sorted(collisions):
                print("   ", next(r[1] for r in rows if r[0] == pid)[:70])
            return 1

        by_category: dict[str, int] = {}
        for row in doomed:
            key = row[2] or "(no category)"
            by_category[key] = by_category.get(key, 0) + 1

        print(f"products in catalogue : {len(rows)}")
        print(f"unparseable, to delete: {len(doomed_ids)}")
        for key, count in sorted(by_category.items(), key=lambda kv: -kv[1]):
            print(f"    stored as {key:16} {count}")
        print("\nsample:")
        for row in doomed[:10]:
            print(f"    [{row[2] or '-'}] {row[1][:64]}")

        if not apply:
            print("\nDRY RUN -- pass --apply to delete.")
            return 0

        db.execute(text("delete from products where id = any(:ids)"), {"ids": doomed_ids})
        db.commit()
        print(f"\nDeleted {len(doomed_ids)} products.")
        print(
            "remaining products",
            db.execute(text("select count(*) from products")).scalar(),
            "| aliases",
            db.execute(text("select count(*) from product_aliases")).scalar(),
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
