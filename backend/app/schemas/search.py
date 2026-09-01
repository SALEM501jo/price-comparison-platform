"""
Response models for tiered product search.

The shape is deliberately grouped rather than a flat ranked list: the whole
point of the feature is that an exact match and a 75% match are qualitatively
different answers, and the UI should be able to say so without re-deriving the
thresholds itself.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class MatchDifference(BaseModel):
    """One attribute on which a candidate differs from the query.

    Deliberately NOT a sentence. The server used to send "different colour
    (blue, not black)" ready-made, which meant the explanation the whole
    tiered-search feature exists to produce arrived in English on an
    Arabic-first site, past the reach of any client translation.

    The client composes the sentence from these fields. `attribute` is the
    stable machine name -- the key a translation table can be written
    against -- while `label` is the English wording, kept so a consumer with
    no translation table of its own still has something to print.
    """

    attribute: str = Field(..., description="Machine name, e.g. 'color'")
    label: str = Field(..., description="English wording, e.g. 'colour'")
    query_value: str = Field(..., description="What the shopper asked for")
    candidate_value: Optional[str] = Field(
        None,
        description="What this product has. Null means the listing does not "
        "state it, which is a different fact from having a different value "
        "and reads as a different sentence.",
    )


class MatchedProduct(BaseModel):
    id: int
    canonical_name: str
    brand: Optional[str] = None
    category: Optional[str] = None
    image_url: Optional[str] = None
    attributes: Optional[Dict[str, str]] = None

    # Price comparison
    lowest_price: Optional[float] = None
    highest_price: Optional[float] = None
    lowest_total_cost: Optional[float] = Field(
        None, description="Lowest price + delivery, which is what a buyer pays"
    )
    store_count: int = Field(0, description="Stores currently listing it in stock")
    best_deal_store: Optional[str] = None

    # NEW UNITS ONLY, all four fields above. Second-hand stock is reported
    # separately below rather than folded in, because a worn handset at 620
    # would otherwise become this product's headline price and every product
    # with one used listing would look like a bargain it is not.
    second_hand_from: Optional[float] = Field(
        None, description="Cheapest used or refurbished total, if any"
    )
    second_hand_store_count: int = Field(
        0, description="Stores listing this second-hand and in stock"
    )

    # Match explanation
    match_score: float = Field(..., description="0-100, weighted attribute agreement")
    match_tier: str = Field(..., description="exact | close | similar")
    differences: List[MatchDifference] = Field(
        default_factory=list,
        description="Which attributes differ, and how. The client turns these "
        "into a sentence in the reader's language.",
    )


class SearchInterpretation(BaseModel):
    """What the server understood the query to mean.

    Surfacing this is what lets the UI explain a surprising result set, and it
    makes the matching debuggable from the outside.
    """

    query: str
    category: Optional[str] = None
    attributes: Dict[str, str] = Field(default_factory=dict)
    structured: bool = Field(
        ...,
        description="True when the query parsed into attributes; False means "
        "results came from a plain name search instead.",
    )

    # A spelling correction the server applied, if any. Reported rather than
    # applied silently: answering a different question from the one asked,
    # without saying so, is how somebody ends up buying the wrong phone.
    corrected_query: Optional[str] = Field(
        None,
        description="The query actually searched, when it differs from what "
        "was typed. Null when nothing was corrected.",
    )
    corrections: Dict[str, str] = Field(
        default_factory=dict,
        description="{typed: corrected} for each word changed",
    )


class TierCounts(BaseModel):
    """How many matched each tier BEFORE pagination.

    Needed because the lists are paginated per tier: without these the UI
    cannot tell "3 exact matches" from "3 shown of 40".
    """

    exact: int = 0
    close: int = 0
    similar: int = 0


class TieredSearchResponse(BaseModel):
    interpretation: SearchInterpretation
    exact: List[MatchedProduct] = Field(default_factory=list)
    close: List[MatchedProduct] = Field(default_factory=list)
    similar: List[MatchedProduct] = Field(default_factory=list)

    total: int = Field(0, description="Products on this page, across all tiers")
    counts: TierCounts = Field(
        default_factory=TierCounts, description="Total matches per tier"
    )
    page: int = 1
    limit: int = Field(20, description="Maximum products per tier, per page")
    sort: str = "price_asc"
    has_more: bool = Field(
        False, description="True when any tier has further pages"
    )


class SearchSuggestion(BaseModel):
    """One type-ahead suggestion.

    Carries the product id as well as the label so a click can go straight to
    the product rather than running a search that has to find it again.
    """

    product_id: int
    label: str
    brand: Optional[str] = None
    category: Optional[str] = None
