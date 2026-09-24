"""
"Samsung A57" and "Galaxy A57" are one phone, and must parse as one model.

THE BUG. Samsung sells its phones as the Galaxy range, and Jordanian stores
write them both ways: SmartBuy's feed says "Samsung A57 5G, 8GB & 256GB",
other listings say "Samsung Galaxy A15 5G 128GB Blue". The two spellings
reached the model attribute through DIFFERENT rules -- the Galaxy pattern
produced "galaxy a 57", the brand-adjacent code rule produced "samsung a57" --
so the engine saw two models where there was one phone.

What that cost, found by the Matching Lab on its first run:

  - SEARCH. A shopper typing "Samsung S24 Ultra", which is how most people
    say it, lost the model's 33 points against every "Galaxy S24 Ultra"
    listing and scored 67 -- excluded, the right phone nowhere on the page.
  - PRICE COMPARISON. Ingest merges two listings only on an exact two-way
    attribute match, so the same handset from a store that writes "Galaxy"
    and one that does not became two products with one price each. The
    site's binding weakness is how few products carry more than one price;
    this split was manufacturing more of them.

THE FIX is one canonical value for both spellings, "galaxy a 57", the form the
Galaxy rule already produced -- so every product whose name says Galaxy keeps
exactly the value it has, and only the "Samsung A57" spelling moves.
"""

import pytest

from app.matching import EXACT, EXCLUDED, parse, score_match
from app.models.alias import ProductAlias
from app.models.product import Product
from app.models.store import Store
from app.services.ingest import IngestService
from app.services.scrapers import ScrapedProduct


def model(title: str) -> str | None:
    return parse(title, hint="Smart Phone").get("model")


class TestOnePhoneOneModel:
    @pytest.mark.parametrize(
        "spellings",
        [
            (
                "Samsung A57 5G, 8GB & 256GB, 6.7Inch, 5000Mah, Dark Blue",
                "Samsung Galaxy A57 5G 256GB Dark Blue",
                "Galaxy A57 256GB",
            ),
            (
                "Samsung S24 Ultra 5G, 12GB & 256GB, Titanium Black",
                "Samsung Galaxy S24 Ultra 256GB Titanium Gray",
                "Galaxy S24 Ultra",
            ),
            ("Samsung Note 20 Ultra 256GB", "Samsung Galaxy Note 20 Ultra 256GB"),
            # Filler between the marque and the code, as AmmanCart writes it.
            ("Samsung Smart Phone A15 128GB", "Samsung Galaxy A15 5G 128GB Blue"),
            # A space inside the code, which the Galaxy rule always allowed.
            ("Samsung A 57 256GB", "Galaxy A57 256GB"),
        ],
    )
    def test_every_spelling_reaches_the_same_model(self, spellings):
        models = {model(title) for title in spellings}
        assert len(models) == 1, models
        assert None not in models

    def test_the_galaxy_form_is_the_canonical_one(self):
        """
        Every product whose name says Galaxy keeps the value it already has.

        The stored attributes of those rows are therefore still right, and
        only the "Samsung A57" spelling moves (see the backfill note in
        HANDOFF.md).
        """
        assert model("Samsung Galaxy S24 128GB Black") == "galaxy s 24"
        assert model("Samsung A57 5G, 8GB & 256GB") == "galaxy a 57"

    @pytest.mark.parametrize(
        "one,other",
        [
            ("Samsung A57 256GB", "Galaxy A56 256GB"),
            ("Samsung S24 256GB", "Galaxy S23 256GB"),
            ("Samsung A15 128GB", "Galaxy M15 128GB"),
        ],
    )
    def test_different_phones_stay_different(self, one, other):
        """Unifying the spelling must not unify the number or the series."""
        assert model(one) != model(other)


class TestSearch:
    @pytest.mark.parametrize(
        "query,listing",
        [
            ("Samsung S24 Ultra 256GB", "Samsung Galaxy S24 Ultra 256GB Titanium Gray"),
            ("Galaxy A57 256GB", "Samsung A57 5G, 8GB & 256GB, 6.7Inch, 5000Mah, Dark Blue"),
            ("سامسونج A57 256 جيجا", "Samsung Galaxy A57 5G 256GB Dark Blue"),
        ],
    )
    def test_the_shoppers_spelling_finds_the_stores(self, query, listing):
        parsed_query = parse(query, require_evidence=False, apply_defaults=False)
        result = score_match(parsed_query, parse(listing, hint="Mobile"))
        assert result.tier == EXACT, result

    def test_a_different_generation_is_still_excluded(self):
        parsed_query = parse("Samsung S24 Ultra 256GB", require_evidence=False, apply_defaults=False)
        listing = parse("Samsung Galaxy S23 Ultra 256GB Phantom Black", hint="Mobile")
        assert score_match(parsed_query, listing).tier == EXCLUDED


class TestAccessoriesAreStillNotPhones:
    """The canonical rule must not reach across a name any more than the old one."""

    @pytest.mark.parametrize(
        "title",
        [
            "Samsung Galaxy Buds 3 Pro",
            "Samsung 32 inch M5 Smart Monitor",
            'Samsung 55" U8000F Crystal UHD 4K Smart TV',
        ],
    )
    def test_not_a_phone(self, title):
        assert parse(title).category != "phones"


class TestTwoStoresOneProduct:
    """
    The consequence that matters most, through the real ingest path.

    Two stores selling the same handset, one writing Galaxy and one not, must
    end up as ONE product with two prices -- which is the whole product.
    """

    @pytest.fixture
    def stores(self, db):
        rows = [
            Store(name="SmartBuy", website="smartbuy-me.com", is_verified=True),
            Store(name="iGeek Megastore", website="igeekjo.com", is_verified=True),
        ]
        db.add_all(rows)
        db.commit()
        return rows

    @staticmethod
    def listing(sku, name, price, host):
        return ScrapedProduct(
            store_product_id=sku,
            name=name,
            price=price,
            currency="JOD",
            availability=True,
            url=f"https://{host}/products/{sku}",
            brand="Samsung",
            category="Smart Phone",
        )

    def test_galaxy_and_plain_spellings_merge(self, db, stores):
        smartbuy, igeek = stores
        service = IngestService(db)
        service.ingest_one(
            smartbuy,
            self.listing(
                "SB-A57",
                "Samsung A57 5G, 8GB & 256GB, 6.7Inch, 5000Mah, Dark Blue",
                329.0,
                "smartbuy-me.com",
            ),
        )
        service.ingest_one(
            igeek,
            self.listing(
                "IG-A57", "Samsung Galaxy A57 5G 8GB 256GB Dark Blue", 315.0, "igeekjo.com"
            ),
        )

        assert db.query(Product).count() == 1
        product = db.query(Product).one()
        stores_listing_it = {alias.store_id for alias in product.aliases}
        assert stores_listing_it == {smartbuy.id, igeek.id}

    def test_a_different_model_does_not_merge(self, db, stores):
        """The merge is still exact: a neighbouring model stays its own product."""
        smartbuy, igeek = stores
        service = IngestService(db)
        service.ingest_one(
            smartbuy,
            self.listing("SB-A57", "Samsung A57 5G, 8GB & 256GB, Dark Blue", 329.0, "smartbuy-me.com"),
        )
        service.ingest_one(
            igeek,
            self.listing("IG-A56", "Samsung Galaxy A56 5G 8GB 256GB Dark Blue", 289.0, "igeekjo.com"),
        )

        assert db.query(Product).count() == 2
        assert db.query(ProductAlias).count() == 2
