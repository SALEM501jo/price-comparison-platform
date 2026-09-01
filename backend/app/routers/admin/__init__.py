"""
The admin API, assembled from four focused modules.

WHY IT WAS SPLIT: this was one 820-line file covering accounts, roles, store
verification, listing moderation, the scrape queue, price anomalies and the
contact form. Nothing about those belongs together beyond needing the same
guard, and a file that long stops being read and starts being searched.

The URLs are unchanged. main.py includes this package's `router` exactly as it
included the module before, and each sub-router keeps its own paths, so the
split is invisible from outside.
"""

from fastapi import APIRouter

from app.routers.admin import platform, stores, support, users

router = APIRouter()

# Order matters only where paths could shadow one another; these four do not
# overlap, so this is declaration order for a reader rather than for FastAPI.
router.include_router(users.router)
router.include_router(stores.router)
router.include_router(platform.router)
router.include_router(support.router)

__all__ = ["router"]
