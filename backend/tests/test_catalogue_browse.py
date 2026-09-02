"""
Browsing the catalogue: the home page's answer to "what do you even have".

WHY THIS IS TESTED SEPARATELY FROM DEALS: the two look similar and mean
different things. `best_savings` may only ever show a product carried by two
or more shops -- one product in the real catalogue -- and the temptation when
a front page looks empty is to quietly loosen that. These tests pin the
boundary: browse shows single-shop stock, deals never do.
"""

import pytest

from app.models.alias import ProductAlias
from app.models.price import Price
from app.models.product import Product
from app.models.store import Store
from app.services import catalogue


# --- Fixtures ---------------------------------------------------------------


def make_store(db, name, *, owner_user_id=None, verified=False):
    store = Store(
        name=name,
        is_active=1,
        owner_user_id=owner_user_id,
        is_verified=verified,
    )
    db.add(store)
    db.flush()
    return store


def stock(db, store, *, name, category, price, image=True, condition="new",
          available=True, sku=None):
    """One shop's listing of one product, priced."""
    product = Product(
        canonical_name=name,
        match_category=category,
        image_url=f"https://cdn.example/{abs(hash(name)) % 9999}.jpg" if image else None,
    )
    db.add(product)
    db.flush()

    alias = ProductAlias(
        product_id=product.id,
        store_id=store.id,
        store_product_name=name,
        store_product_id=sku or f"sku-{product.id}",
        condition=condition,
    )
    db.add(alias)
    db.flush()

    db.add(Price(alias_id=alias.id, price=price, delivery_cost=0,
                 availability=available))
    db.flush()
    return product


@pytest.fixture
def catalogue_db(db_session):
    """Three categories at different price levels, which is the real shape."""
    shop = make_store(db_session, "iGeek")

    # Monitors are cheap, phones are dear. This is what makes a single global
    # sort by price return nothing but monitors.
    for i in range(4):
        stock(db_session, shop, name=f"Monitor {i}", category="monitors",
              price=69 + i)
    for i in range(4):
        stock(db_session, shop, name=f"Phone {i}", category="phones",
              price=400 + i)
    for i in range(4):
        stock(db_session, shop, name=f"Laptop {i}", category="laptops",
              price=900 + i)

    db_session.commit()
    return db_session


# --- Counts -----------------------------------------------------------------


class TestCategoryCounts:
    def test_counts_what_a_shopper_can_actually_reach(self, catalogue_db):
        counts = {row["category"]: row["count"] for row
                  in catalogue.category_counts(catalogue_db)}
        assert counts == {"phones": 4, "laptops": 4, "monitors": 4}

    def test_out_of_stock_products_are_not_advertised(self, catalogue_db):
        """A tile promising 5 phones that leads to 4 is worse than no tile."""
        shop = catalogue_db.query(Store).first()
        stock(catalogue_db, shop, name="Phone SOLD OUT", category="phones",
              price=500, available=False)
        catalogue_db.commit()

        counts = {row["category"]: row["count"] for row
                  in catalogue.category_counts(catalogue_db)}
        assert counts["phones"] == 4

    def test_an_unverified_merchants_stock_is_invisible(self, catalogue_db):
        """Same rule the prices follow, applied in the query."""
        pending = make_store(catalogue_db, "Pending Shop", owner_user_id=1,
                             verified=False)
        stock(catalogue_db, pending, name="Phone Pending", category="phones",
              price=500)
        catalogue_db.commit()

        counts = {row["category"]: row["count"] for row
                  in catalogue.category_counts(catalogue_db)}
        assert counts["phones"] == 4

    def test_an_empty_category_is_dropped_not_shown_as_zero(self, db_session):
        shop = make_store(db_session, "Phones Only")
        stock(db_session, shop, name="Phone A", category="phones", price=400)
        db_session.commit()

        assert [row["category"] for row in catalogue.category_counts(db_session)] == [
            "phones"
        ]


# --- Browsing ---------------------------------------------------------------


class TestBrowse:
    def test_the_mixed_view_spreads_across_categories(self, catalogue_db):
        """
        THE POINT OF THE FUNCTION. Ranking the whole catalogue by price returns
        nothing but monitors, because the cheapest monitor is 69 and the
        cheapest phone is 400 -- so the front page of a phone-led comparison
        site silently becomes a monitor aisle.
        """
        rows = catalogue.browse(catalogue_db, limit=9)
        categories = {row["category"] for row in rows}
        assert categories == {"phones", "laptops", "monitors"}
        assert len(rows) == 9

    def test_a_named_category_returns_only_that_category(self, catalogue_db):
        rows = catalogue.browse(catalogue_db, category="phones", limit=5)
        assert rows
        assert {row["category"] for row in rows} == {"phones"}

    def test_within_a_category_the_cheapest_comes_first(self, catalogue_db):
        rows = catalogue.browse(catalogue_db, category="phones", limit=4)
        totals = [row["lowest_total_cost"] for row in rows]
        assert totals == sorted(totals)

    def test_delivery_is_included_in_the_price_shown(self, catalogue_db):
        """The figure is what a buyer pays, as everywhere else in this app."""
        shop = catalogue_db.query(Store).first()
        product = stock(catalogue_db, shop, name="Phone Delivered",
                        category="phones", price=100)
        alias = (catalogue_db.query(ProductAlias)
                 .filter(ProductAlias.product_id == product.id).one())
        price = catalogue_db.query(Price).filter(Price.alias_id == alias.id).one()
        price.delivery_cost = 5
        catalogue_db.commit()

        row = next(r for r in catalogue.browse(catalogue_db, category="phones",
                                               limit=10)
                   if r["id"] == product.id)
        assert row["lowest_total_cost"] == 105.0

    def test_a_product_with_no_picture_sorts_last_but_is_not_hidden(self, catalogue_db):
        """
        Five of 423 real products have no image. Dropping them would quietly
        hide real stock; letting them lead would put placeholder tiles at the
        top of the front page.
        """
        shop = catalogue_db.query(Store).first()
        cheapest = stock(catalogue_db, shop, name="Phone No Photo",
                         category="phones", price=1, image=False)
        catalogue_db.commit()

        rows = catalogue.browse(catalogue_db, category="phones", limit=10)
        ids = [row["id"] for row in rows]
        assert cheapest.id in ids, "a product without a photo must still be reachable"
        assert ids[-1] == cheapest.id, "it must not lead the page despite being cheapest"

    def test_second_hand_stock_is_left_out(self, catalogue_db):
        """A worn unit is not a cheaper version of the same offer."""
        shop = catalogue_db.query(Store).first()
        used = stock(catalogue_db, shop, name="Phone Used", category="phones",
                     price=1, condition="used")
        catalogue_db.commit()

        ids = [row["id"] for row in catalogue.browse(catalogue_db,
                                                     category="phones", limit=10)]
        assert used.id not in ids

    def test_an_unverified_merchants_stock_is_invisible(self, catalogue_db):
        pending = make_store(catalogue_db, "Pending Shop", owner_user_id=1,
                             verified=False)
        hidden = stock(catalogue_db, pending, name="Phone Pending",
                       category="phones", price=1)
        catalogue_db.commit()

        ids = [row["id"] for row in catalogue.browse(catalogue_db, limit=20)]
        assert hidden.id not in ids

    def test_it_names_the_cheapest_shop(self, catalogue_db):
        rows = catalogue.browse(catalogue_db, category="phones", limit=1)
        assert rows[0]["best_deal_store"] == "iGeek"

    def test_an_empty_catalogue_returns_nothing_rather_than_failing(self, db_session):
        assert catalogue.browse(db_session, limit=12) == []
        assert catalogue.category_counts(db_session) == []

    def test_the_limit_is_respected_even_when_categories_are_lopsided(self, db_session):
        """
        The round-robin pads short categories. Without the padding, zip() would
        stop at the shortest and silently lose the tail of the long one.
        """
        shop = make_store(db_session, "Lopsided")
        for i in range(6):
            stock(db_session, shop, name=f"Phone {i}", category="phones",
                  price=400 + i)
        stock(db_session, shop, name="Only Monitor", category="monitors", price=70)
        db_session.commit()

        rows = catalogue.browse(db_session, limit=5)
        assert len(rows) == 5
        # The single monitor is present, and the phones fill the rest.
        assert sum(1 for r in rows if r["category"] == "monitors") == 1
        assert sum(1 for r in rows if r["category"] == "phones") == 4


# --- The endpoint -----------------------------------------------------------


class TestBrowseEndpoint:
    def test_it_returns_categories_and_products_together(self, client, catalogue_db):
        response = client.get("/products/browse", params={"limit": 6})
        assert response.status_code == 200

        body = response.json()
        assert {row["category"] for row in body["categories"]} == {
            "phones", "laptops", "monitors"
        }
        assert len(body["products"]) == 6

    def test_it_can_be_filtered_to_one_category(self, client, catalogue_db):
        body = client.get(
            "/products/browse", params={"category": "monitors", "limit": 4}
        ).json()
        assert {p["category"] for p in body["products"]} == {"monitors"}

    def test_browse_is_not_read_as_a_product_id(self, client, catalogue_db):
        """
        /browse is declared before /{product_id}. With the dynamic route first
        FastAPI parses "browse" as an integer id and 422s -- the same trap
        /deals and /suggest are declared early to avoid.
        """
        assert client.get("/products/browse").status_code == 200

    def test_every_product_carries_what_a_tile_needs(self, client, catalogue_db):
        product = client.get("/products/browse", params={"limit": 1}).json()["products"][0]
        for field in ("id", "canonical_name", "image_url", "lowest_total_cost",
                      "best_deal_store", "store_count", "category"):
            assert field in product, f"tile cannot render without {field}"

    def test_a_single_shop_product_appears_here_but_never_in_deals(
        self, client, catalogue_db
    ):
        """
        The line this whole module exists to hold. Every fixture product is
        stocked by exactly ONE shop, so deals must be empty while browse is
        full. A future change that "fixes" the empty deals grid by relaxing
        the two-shop rule fails here.
        """
        browsed = client.get("/products/browse", params={"limit": 12}).json()
        assert browsed["products"], "single-shop stock must be browsable"
        assert client.get("/products/deals").json() == []


# --- Paging -----------------------------------------------------------------


class TestPaging:
    """
    A category tile advertises a number -- "151 products" -- so the page behind
    it has to be able to reach all 151. Everything here exists because that
    promise is on the home page.
    """

    def test_the_total_counts_products_not_offers(self, catalogue_db):
        """
        A product carried by three shops is ONE thing to look at. Counting
        offers would promise pages that do not exist.
        """
        shop_a = catalogue_db.query(Store).first()
        shop_b = make_store(catalogue_db, "Second Shop")

        # Same product name in a second shop: dedup gives it its own alias and
        # price but it must not add to the count.
        product = stock(catalogue_db, shop_a, name="Shared Phone",
                        category="phones", price=500)
        alias = ProductAlias(
            product_id=product.id, store_id=shop_b.id,
            store_product_name="Shared Phone", store_product_id="sku-b",
            condition="new",
        )
        catalogue_db.add(alias)
        catalogue_db.flush()
        catalogue_db.add(Price(alias_id=alias.id, price=490, delivery_cost=0,
                               availability=True))
        catalogue_db.commit()

        assert catalogue.total_in(catalogue_db, "phones") == 5

    def test_the_total_respects_the_same_filters_as_the_listing(self, catalogue_db):
        pending = make_store(catalogue_db, "Pending", owner_user_id=1, verified=False)
        stock(catalogue_db, pending, name="Hidden Phone", category="phones", price=1)
        stock(catalogue_db, catalogue_db.query(Store).first(),
              name="Used Phone", category="phones", price=1, condition="used")
        catalogue_db.commit()

        assert catalogue.total_in(catalogue_db, "phones") == 4

    def test_a_second_page_does_not_repeat_the_first(self, catalogue_db):
        first = catalogue.browse(catalogue_db, category="phones", limit=2, offset=0)
        second = catalogue.browse(catalogue_db, category="phones", limit=2, offset=2)
        assert len(first) == len(second) == 2
        assert not {r["id"] for r in first} & {r["id"] for r in second}

    def test_paging_the_mixed_view_keeps_interleaving(self, catalogue_db):
        """
        Page 2 of a round-robin is NOT the round-robin of each category's page
        2, which is why the offset is applied after interleaving rather than
        pushed into each query.
        """
        first = catalogue.browse(catalogue_db, limit=3, offset=0)
        second = catalogue.browse(catalogue_db, limit=3, offset=3)
        assert {r["category"] for r in second} == {"phones", "laptops", "monitors"}
        assert not {r["id"] for r in first} & {r["id"] for r in second}

    def test_paging_past_the_end_is_empty_rather_than_an_error(self, catalogue_db):
        assert catalogue.browse(catalogue_db, category="phones",
                                limit=10, offset=500) == []


class TestPagingEndpoint:
    def test_it_reports_the_total_and_whether_more_remain(self, client, catalogue_db):
        body = client.get("/products/browse",
                          params={"category": "phones", "limit": 2}).json()
        assert body["total"] == 4
        assert body["page"] == 1
        assert len(body["products"]) == 2
        assert body["has_more"] is True

    def test_the_last_page_says_there_is_no_more(self, client, catalogue_db):
        """
        has_more is computed from the TOTAL, not from a short page: a full
        final page would otherwise claim there is another one after it.
        """
        body = client.get("/products/browse",
                          params={"category": "phones", "limit": 2, "page": 2}).json()
        assert len(body["products"]) == 2
        assert body["has_more"] is False

    def test_pages_do_not_overlap_over_http(self, client, catalogue_db):
        one = client.get("/products/browse",
                         params={"category": "phones", "limit": 2, "page": 1}).json()
        two = client.get("/products/browse",
                         params={"category": "phones", "limit": 2, "page": 2}).json()
        assert not ({p["id"] for p in one["products"]}
                    & {p["id"] for p in two["products"]})

    def test_the_advertised_count_is_reachable(self, client, catalogue_db):
        """
        THE REGRESSION THIS MODULE EXISTS FOR. The home page tile says
        "N products"; walking the pages must actually yield N. The tiles used
        to link to a text SEARCH for the category word instead, which returned
        nothing for phones and one unrelated monitor for laptops.
        """
        advertised = next(
            row["count"]
            for row in client.get("/products/browse").json()["categories"]
            if row["category"] == "phones"
        )

        seen, page = set(), 1
        while True:
            body = client.get("/products/browse",
                              params={"category": "phones", "limit": 2,
                                      "page": page}).json()
            seen.update(p["id"] for p in body["products"])
            if not body["has_more"]:
                break
            page += 1
            assert page < 20, "paging did not terminate"

        assert len(seen) == advertised
