"""
Product deduplication -- ENTITY RESOLUTION at ingest time.

THE PROBLEM: Store A calls it "iPhone 15 128GB 5G - Black"
             Store B calls it "Apple iPhone 15 128GB Black (5G)"
             Store C calls it "iPhone 15 128GB Midnight"

             SAME PRODUCT. THREE NAMES.

Note this is a DIFFERENT problem from search relevance, even though both
compare product names:

  entity resolution (here)  -- "are these the same product?" -> merge or don't,
                               binary, needs high PRECISION because a wrong
                               merge shows one phone's price under another
  search relevance (scorer) -- "which products answer this query?" -> ranked
                               tiers, tolerant of near-misses by design

Both parse names with app.matching.parse, which is what makes their attributes
comparable. They differ in what they do with the score: this module merges only
on an exact, symmetric attribute match.
"""

from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.matching import EXACT, parse, score_match
from app.models.alias import ProductAlias
from app.models.product import Product


class DeduplicationEngine:
    """
    Two-layer matching:

    Layer 1: SKU exact match           -- 1.00 confidence, one indexed lookup
    Layer 2: symmetric attribute match -- 0.95 confidence

    Layer 2 requires the two names to agree on EVERY attribute in BOTH
    directions. Scoring one-way would over-merge: a bare "iPhone 11 Pro"
    listing scores 100 against "iPhone 11 Pro 128GB Black", because attributes
    the query omits are not penalised. That is correct for search and wrong
    for deciding two listings are the same physical product.
    """

    def __init__(self, db: Session):
        self.db = db

    # --- lookup helpers ----------------------------------------------------

    def _find_existing_alias(
        self,
        store_id: int,
        store_product_name: str,
        store_product_id: Optional[str] = None,
    ) -> Optional[ProductAlias]:
        """
        Look up the alias this exact store listing already maps to.

        Scoped by store_id: two stores can legitimately reuse the same SKU
        string, so matching on store_product_id alone would cross-link them.
        """
        q = self.db.query(ProductAlias).filter(ProductAlias.store_id == store_id)
        if store_product_id:
            hit = q.filter(ProductAlias.store_product_id == store_product_id).first()
            if hit:
                return hit
        return q.filter(
            ProductAlias.store_product_name == store_product_name
        ).first()

    def _candidates(self, parsed) -> list[Product]:
        """
        Narrow the search space before scoring.

        Filtering on the indexed (match_category, brand) pair keeps this from
        loading the whole product table, which is what the previous
        implementation did on every single incoming listing.
        """
        query = self.db.query(Product).filter(
            Product.match_category == parsed.category
        )
        brand = parsed.get("brand")
        if brand:
            query = query.filter(Product.brand == brand)
        return query.all()

    # --- matching ----------------------------------------------------------

    def find_match(
        self,
        store_product_name: str,
        store_product_id: Optional[str] = None,
        store_id: Optional[int] = None,
    ) -> Tuple[Optional[Product], float, str]:
        """
        Try to resolve a store listing to an existing canonical product.

        Returns: (product_or_none, confidence, method)
        """
        # === LAYER 1: SKU exact match ===
        if store_product_id:
            q = self.db.query(ProductAlias).filter(
                ProductAlias.store_product_id == store_product_id
            )
            if store_id is not None:
                q = q.filter(ProductAlias.store_id == store_id)
            existing = q.first()
            if existing:
                return existing.product, 1.0, "sku"

        # === LAYER 2: symmetric attribute match ===
        incoming = parse(store_product_name)

        for candidate in self._candidates(incoming):
            other = parse(
                candidate.canonical_name, category=candidate.match_category
            )
            forward = score_match(incoming, other)
            if forward.tier != EXACT:
                continue
            if score_match(other, incoming).tier != EXACT:
                continue  # candidate carries attributes the listing does not
            return candidate, 0.95, "attributes"

        return None, 0.0, "none"

    # --- writes ------------------------------------------------------------

    def create_alias(
        self,
        product_id: int,
        store_id: int,
        store_product_name: str,
        store_product_id: Optional[str] = None,
        store_product_url: Optional[str] = None,
        confidence: float = 0.0,
        method: str = "manual",
    ) -> ProductAlias:
        """Map one store's naming of a product onto the canonical product."""
        alias = ProductAlias(
            product_id=product_id,
            store_id=store_id,
            store_product_name=store_product_name,
            store_product_id=store_product_id,
            store_product_url=store_product_url,
            match_confidence=confidence,
            match_method=method,
        )
        self.db.add(alias)
        self.db.commit()
        self.db.refresh(alias)
        return alias

    def process_new_product(
        self,
        store_id: int,
        store_product_name: str,
        store_product_id: Optional[str] = None,
        store_product_url: Optional[str] = None,
        brand: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Tuple[Product, ProductAlias, bool]:
        """
        Main entry point: ingest one listing from one store.

        Returns: (product, alias, is_new_product)
        """
        # IDEMPOTENCY GUARD -- must run first.
        # The scraper re-processes every listing on every run. Without this, a
        # listing we have already seen fell through to create_alias() and
        # inserted a duplicate alias, which made the scraper insert a duplicate
        # Price too: four runs meant four aliases and four prices for one
        # product at one store, inflating store_count and preventing
        # PriceHistory from ever recording a change.
        existing_alias = self._find_existing_alias(
            store_id, store_product_name, store_product_id
        )
        if existing_alias:
            return existing_alias.product, existing_alias, False

        existing_product, confidence, method = self.find_match(
            store_product_name, store_product_id, store_id
        )

        if existing_product:
            alias = self.create_alias(
                product_id=existing_product.id,
                store_id=store_id,
                store_product_name=store_product_name,
                store_product_id=store_product_id,
                store_product_url=store_product_url,
                confidence=confidence,
                method=method,
            )
            return existing_product, alias, False

        # No match -- this listing defines a new canonical product.
        parsed = parse(store_product_name)

        new_product = Product(
            # The store's own wording, NOT a normalised form. Normalising for
            # comparison lowercases and strips words, and the result was being
            # rendered in the UI as the product's name.
            canonical_name=store_product_name,
            brand=brand or parsed.get("brand") or "Unknown",
            category=category or "Uncategorized",
            match_category=parsed.category,
            match_attributes=parsed.specified,
            specs=parsed.specified,
        )
        self.db.add(new_product)
        self.db.commit()
        self.db.refresh(new_product)

        alias = self.create_alias(
            product_id=new_product.id,
            store_id=store_id,
            store_product_name=store_product_name,
            store_product_id=store_product_id,
            store_product_url=store_product_url,
            confidence=1.0,  # the first alias is the definition
            method="canonical",
        )

        return new_product, alias, True
