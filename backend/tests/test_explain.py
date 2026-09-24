"""
The Matching Lab's explanation of a search (services/explain.py).

Two things are pinned here. The explanation must be the SITE'S reading --
same query reading, same listing parse, same scores -- or the Lab explains a
search nobody runs. And the string-similarity baseline must be the one the
project's argument was measured with, or the comparison the Lab draws is
against a straw man.
"""

import random

import pytest
from pydantic import ValidationError

from app.schemas.explain import MAX_LISTINGS, MAX_TITLE, ExplainRequest
from app.services.explain import explain, lcs_length, string_similarity

README_QUERY = "iPhone 11 Pro Black 128GB"

# README.md's table, in its order: the listings test_matching.py scores.
README_LISTINGS = [
    "Apple iPhone 11 Pro 128GB Black",
    "iPhone 11 Pro Black 128GB Smartphone 5G",
    "Apple iPhone 11 Pro 128GB Midnight Green",
    "Apple iPhone 11 Pro 256GB Black",
    "Apple iPhone 11 Pro Max 128GB Black",
    "Apple iPhone 12 Pro 128GB Black",
    "Samsung Galaxy S24 128GB Black",
]


def run(query, listings, correct=True):
    """Explain `query` against listings given as titles or (title, store category)."""
    body = ExplainRequest(
        query=query,
        listings=[
            {"title": item, "store_category": None}
            if isinstance(item, str)
            else {"title": item[0], "store_category": item[1]}
            for item in listings
        ],
        correct=correct,
    )
    return explain(body)


def textbook_lcs(a: str, b: str) -> int:
    table = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i, ca in enumerate(a, 1):
        for j, cb in enumerate(b, 1):
            table[i][j] = (
                table[i - 1][j - 1] + 1
                if ca == cb
                else max(table[i - 1][j], table[i][j - 1])
            )
    return table[-1][-1]


class TestTheBaseline:
    def test_bit_parallel_lcs_agrees_with_the_table(self):
        rng = random.Random(20260924)
        alphabet = "ab1 2gبس"
        for _ in range(500):
            a = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
            b = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
            assert lcs_length(a, b) == textbook_lcs(a, b), (a, b)

    def test_it_reproduces_the_measurement_scorer_py_documents(self):
        """
        "the listing 'Apple iPhone 11 Pro 128GB Black' scored 67.9 against the
        query 'iPhone 11 Pro Black 128GB' -- tying exactly with the 256GB
        model ... and ranking BELOW the Pro Max." -- matching/scorer.py
        """
        right = string_similarity(README_QUERY, "Apple iPhone 11 Pro 128GB Black")
        wrong_storage = string_similarity(README_QUERY, "Apple iPhone 11 Pro 256GB Black")
        pro_max = string_similarity(README_QUERY, "Apple iPhone 11 Pro Max 128GB Black")

        assert right == 67.9
        assert wrong_storage == right
        assert pro_max == 70.0 > right

    def test_it_is_given_the_same_clean_text_as_the_engine(self):
        """Case, punctuation and script are not what separates the two methods."""
        assert string_similarity("IPHONE 15", "iphone 15") == 100.0
        assert string_similarity("ايفون ١٥", "iPhone 15") == 100.0


class TestTheReadmeExample:
    def test_scores_are_the_engines(self):
        result = run(README_QUERY, README_LISTINGS)
        assert [(l.score, l.tier) for l in result.listings] == [
            (100.0, "exact"),
            (100.0, "exact"),
            (90.0, "close"),
            (76.0, "similar"),
            (72.0, "similar"),
            (67.0, "excluded"),
            (0.0, "excluded"),
        ]

    def test_each_listing_says_what_differed(self):
        listings = run(README_QUERY, README_LISTINGS).listings
        lost = [
            [(c.attribute, c.query_value, c.candidate_value) for c in l.comparisons if not c.matched]
            for l in listings
        ]
        assert lost[2] == [("color", "black", "midnight green")]
        assert lost[3] == [("storage", "128gb", "256gb")]
        assert lost[4] == [("variant", "pro", "pro max")]
        assert lost[5] == [("model", "iphone 11", "iphone 12")]

    def test_brand_is_a_gate_not_a_deduction(self):
        samsung = run(README_QUERY, README_LISTINGS).listings[6]
        assert samsung.outcome == "gated"
        assert (samsung.gate.attribute, samsung.gate.query_value, samsung.gate.candidate_value) == (
            "brand",
            "apple",
            "samsung",
        )
        assert samsung.comparisons == []

    def test_the_two_methods_disagree_where_the_readme_says(self):
        """A one-character edit ties; a different phone outranks the right one."""
        by_title = {l.title: l for l in run(README_QUERY, README_LISTINGS).listings}
        right = by_title["Apple iPhone 11 Pro 128GB Black"]
        wrong_storage = by_title["Apple iPhone 11 Pro 256GB Black"]
        pro_max = by_title["Apple iPhone 11 Pro Max 128GB Black"]

        assert right.string_similarity == wrong_storage.string_similarity
        assert pro_max.string_similarity > right.string_similarity
        assert right.score > wrong_storage.score > pro_max.score

    def test_the_query_carries_its_categorys_weights(self):
        query = run(README_QUERY, README_LISTINGS).query
        assert query.category == "phones"
        weights = {w.attribute: (w.weight, w.gate) for w in query.weights}
        assert weights == {
            "brand": (0, True),
            "model": (33, False),
            "variant": (28, False),
            "storage": (24, False),
            "ram": (5, False),
            "color": (10, False),
        }
        assert sum(w for w, gate in weights.values() if not gate) == 100


class TestReadingTheQuery:
    def test_arabic_is_shown_folded_into_the_engines_words(self):
        query = run("ايفون ١٥ ١٢٨ جيجا اسود", ["iPhone 15 128GB Midnight"]).query
        assert [s.stage for s in query.steps] == ["typed", "arabic", "normalized"]
        assert query.steps[1].text == "iphone 15 128 gb black"
        assert query.attributes == {
            "brand": "apple",
            "model": "iphone 15",
            "storage": "128gb",
            "color": "black",
        }

    def test_midnight_is_black(self):
        listing = run("ايفون ١٥ ١٢٨ جيجا اسود", ["iPhone 15 128GB Midnight"]).listings[0]
        assert (listing.score, listing.tier) == (100.0, "exact")

    def test_a_latin_query_has_no_arabic_step(self):
        steps = run(README_QUERY, README_LISTINGS[:1]).query.steps
        assert [s.stage for s in steps] == ["typed", "normalized"]

    def test_a_spelling_correction_is_reported_as_a_step(self):
        query = run("smasung s24 ultra 256gb", ["Samsung Galaxy S24 Ultra 256GB"]).query
        assert query.corrections == {"smasung": "samsung"}
        assert query.corrected_query == "samsung s24 ultra 256gb"
        assert [s.stage for s in query.steps] == ["typed", "spelling", "normalized"]

    def test_correction_can_be_refused_as_search_allows(self):
        result = run("smasung s24 ultra 256gb", ["Samsung Galaxy S24 Ultra 256GB"], correct=False)
        assert result.query.corrections == {}
        assert result.query.category is None
        assert result.listings[0].outcome == "query_unread"


class TestWhyAListingDidNotScore:
    def test_a_case_is_turned_away_by_the_stores_own_category(self):
        """
        The example string similarity gets most wrong: the case repeats the
        query word for word, so it outranks the phone by a mile.
        """
        case, phone = run(
            "iPhone 15 Pro",
            [
                ("IPHONE 15 PRO CASE", "Mobile Case"),
                ("Apple iPhone 15 Pro 256GB Natural Titanium", "iPhone 15"),
            ],
        ).listings

        assert case.outcome == "refused_by_store"
        assert case.category is None
        assert phone.tier == "exact"
        assert case.string_similarity > phone.string_similarity

    def test_an_unreadable_listing_is_not_blamed_on_the_store(self):
        listing = run("iPhone 15 Pro", [("Wireless Charger 15W", None)]).listings[0]
        assert listing.outcome == "unrecognised"

    def test_a_laptop_is_not_scored_against_a_phone_search(self):
        listing = run("iPhone 15 128GB", ["Apple MacBook Air M3 16GB 512GB"]).listings[0]
        assert listing.outcome == "other_category"
        assert listing.score == 0.0

    def test_a_query_naming_only_a_brand_has_nothing_to_score(self):
        """"iphone a16" is brand=apple and nothing else: A16 is the chip."""
        listing = run("iphone a16", ["Apple iPhone 16 128GB Black"]).listings[0]
        assert listing.outcome == "nothing_to_score"

    def test_a_query_the_engine_cannot_read_says_so(self):
        result = run("playstation", ["Apple iPhone 16 128GB Black"])
        assert result.query.category is None
        assert result.query.weights == []
        assert result.listings[0].outcome == "query_unread"


class TestBounds:
    def test_too_many_listings(self):
        with pytest.raises(ValidationError):
            ExplainRequest(query="iphone", listings=[{"title": "x"}] * (MAX_LISTINGS + 1))

    def test_too_long_a_title(self):
        with pytest.raises(ValidationError):
            ExplainRequest(query="iphone", listings=[{"title": "x" * (MAX_TITLE + 1)}])

    def test_no_listings(self):
        with pytest.raises(ValidationError):
            ExplainRequest(query="iphone", listings=[])


class TestTheRoute:
    def test_explains_over_http(self, client):
        response = client.post(
            "/products/explain",
            json={
                "query": README_QUERY,
                "listings": [{"title": t} for t in README_LISTINGS[:2]],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["query"]["category"] == "phones"
        assert [l["tier"] for l in body["listings"]] == ["exact", "exact"]
        assert body["listings"][0]["string_similarity"] == 67.9

    def test_refuses_oversized_input(self, client):
        response = client.post(
            "/products/explain",
            json={"query": README_QUERY, "listings": [{"title": "x"}] * (MAX_LISTINGS + 1)},
        )
        assert response.status_code == 422

    def test_a_query_search_would_refuse_is_refused_here_too(self, client):
        response = client.post(
            "/products/explain", json={"query": "x", "listings": [{"title": "iPhone 15"}]}
        )
        assert response.status_code == 422

    def test_reading_it_with_get_does_not_serve_the_app(self, client):
        """/products is an API prefix: an unknown method is an API answer, never the SPA."""
        response = client.get("/products/explain")
        assert response.status_code in (404, 405, 422)
        assert "text/html" not in response.headers.get("content-type", "")
