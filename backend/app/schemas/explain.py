"""
Request and response models for the Matching Lab (services/explain.py).

EVERY INPUT IS BOUNDED. The endpoint is public and does all its work in
Python, so its cost is set here: at most MAX_LISTINGS listings, each title at
most MAX_TITLE characters, and a query no longer than search itself accepts.
Nothing is stored and nothing is fetched.
"""

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

MAX_LISTINGS = 8
MAX_TITLE = 200
# The same bounds as GET /products/search, so the Lab accepts exactly the
# queries the site does and nothing it would refuse.
MIN_QUERY, MAX_QUERY = 2, 100
MAX_STORE_CATEGORY = 60

Outcome = Literal[
    "scored",
    "gated",
    "other_category",
    "nothing_to_score",
    "refused_by_store",
    "unrecognised",
    "query_unread",
]


class ListingIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=MAX_TITLE)
    store_category: Optional[str] = Field(
        None,
        max_length=MAX_STORE_CATEGORY,
        description="The store's own product_type, e.g. 'Mobile' or 'Mobile Case'. "
        "Read exactly as ingest reads it.",
    )


class ExplainRequest(BaseModel):
    query: str = Field(..., min_length=MIN_QUERY, max_length=MAX_QUERY)
    listings: List[ListingIn] = Field(..., min_length=1, max_length=MAX_LISTINGS)
    correct: bool = Field(True, description="Allow spelling correction, as search does")


class ReadingStep(BaseModel):
    """The query's text after one stage that changed it."""

    stage: Literal["typed", "spelling", "arabic", "normalized"]
    text: str


class AttributeWeight(BaseModel):
    """One attribute of the query's category, from rules.py."""

    attribute: str
    label: str
    weight: int
    gate: bool


class ComparisonOut(BaseModel):
    attribute: str
    label: str
    weight: int
    query_value: Optional[str] = None
    candidate_value: Optional[str] = None
    matched: bool


class QueryExplanation(BaseModel):
    query: str
    steps: List[ReadingStep]
    corrected_query: Optional[str] = None
    corrections: Dict[str, str] = Field(default_factory=dict)
    category: Optional[str] = Field(
        None, description="Null when the query named nothing the engine can read"
    )
    attributes: Dict[str, str] = Field(default_factory=dict)
    weights: List[AttributeWeight] = Field(
        default_factory=list,
        description="The category's attributes in rules.py order, gates included",
    )


class ListingExplanation(BaseModel):
    title: str
    store_category: Optional[str] = None
    category: Optional[str] = None
    attributes: Dict[str, str] = Field(default_factory=dict)
    outcome: Outcome
    score: float = Field(..., description="0-100, from score_match; 0 unless scored")
    tier: Literal["exact", "close", "similar", "excluded"]
    comparisons: List[ComparisonOut] = Field(
        default_factory=list,
        description="One per attribute the query asked for. Attributes absent "
        "here were not asked for and cost nothing.",
    )
    gate: Optional[ComparisonOut] = Field(
        None, description="The gate attribute that excluded this listing, if one did"
    )
    string_similarity: float = Field(
        ..., description="0-100 normalised Indel similarity of the cleaned texts"
    )


class ExplainResponse(BaseModel):
    query: QueryExplanation
    listings: List[ListingExplanation] = Field(
        ..., description="In the order they were sent"
    )
