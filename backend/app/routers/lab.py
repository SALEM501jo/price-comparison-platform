"""
The Matching Lab's one route: explain how a search reads and ranks listings.

Mounted under /products beside search, because it answers a question about
search and because /products is already one of the API prefixes the SPA
fallback in app/frontend.py knows. A new top-level prefix would have to be
added there too, and forgetting it gives a route that works by POST while a
GET of the same path returns the app shell.
"""

from fastapi import APIRouter, Depends

from app.dependencies import get_rate_limited
from app.schemas.explain import ExplainRequest, ExplainResponse
from app.services.explain import explain

router = APIRouter()


@router.post("/explain", response_model=ExplainResponse)
async def explain_search(
    body: ExplainRequest,
    _: None = Depends(get_rate_limited),
):
    """
    Read a query and score each listing against it, reporting every step.

    POST rather than GET because the input is a list of listings, not a
    filter. Nothing is written and nothing is fetched: the answer depends only
    on the body and on matching/rules.py, and it is the same computation
    search and ingest perform.

    The public catalogue limit applies (100 a minute per address), and the
    request model caps the work: 8 listings of at most 200 characters.
    """
    return explain(body)
