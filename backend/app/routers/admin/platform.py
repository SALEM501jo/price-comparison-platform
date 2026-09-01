"""
Admin routes for the platform itself: statistics, the scrape queue,
and price anomalies.

Not in the user or store modules because none of it is about a person
or a shop -- it is the operator's view of the machine.
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import require_admin
from app.logging_config import get_security_logger
from app.models.alias import ProductAlias
from app.models.price import Price, PriceHistory
from app.models.product import Product
from app.models.scrape_job import ScrapeJob
from app.models.store import Store
from app.models.user import User
from app.services import jobs as job_queue
from app.services.scrapers import STORES, store_by_code

router = APIRouter()
logger = get_security_logger("app.admin")


@router.get("/stats")
async def get_stats(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin)
):
    """
    Platform statistics. Admin only.
    """
    logger.info("Admin viewing stats", extra={
        "admin_id": admin.id,
        "action": "admin_view_stats"
    })
    
    stats = {
        "users": db.query(func.count(User.id)).scalar(),
        "products": db.query(func.count(Product.id)).scalar(),
        "stores": db.query(func.count(Store.id)).scalar(),
        "aliases": db.query(func.count(ProductAlias.id)).scalar(),
        "prices": db.query(func.count(Price.id)).scalar(),
        "price_history_records": db.query(func.count(PriceHistory.id)).scalar(),
    }
    
    return stats


@router.post("/scrape", status_code=status.HTTP_202_ACCEPTED)
async def trigger_scrape(
    store: str | None = None,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Queue a scrape run. Admin only.

    ENQUEUES, rather than running the work behind the response. The previous
    version used BackgroundTasks, which runs inside the web process: a
    restart killed the run mid-flight, nothing recorded that it had ever
    existed, and the only sign was a log line nobody was watching. A deploy
    during a scrape simply lost it.

    The job is now a row. A worker claims it -- see app/services/worker.py --
    so the work outlives the process that asked for it, survives a deploy, and
    leaves a history the admin screen can show.

    `store` optionally limits the run to one store code.
    """
    targets = STORES
    if store:
        config = store_by_code(store)
        if not config:
            raise HTTPException(
                status_code=404,
                detail=f"Unknown store. Known: {[s.code for s in STORES]}",
            )
        targets = (config,)

    job = job_queue.enqueue(
        db, [s.code for s in targets], requested_by=admin.id
    )

    logger.warning(
        "Admin queued a scrape",
        extra={
            "user_id": admin.id,
            "action": "admin_trigger_scrape",
            "target": ",".join(s.code for s in targets),
            "success": True,
        },
    )

    return {
        "status": "queued",
        "job_id": job.id,
        "stores": [s.name for s in targets],
        "note": "A worker picks this up; watch /admin/scrape-jobs for progress.",
    }


@router.get("/scrape-jobs")
async def list_scrape_jobs(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Recent scrape runs and how they went.

    The reason the queue is a table rather than a background thread: a run
    that failed at three in the morning is answerable here, instead of only
    in server logs nobody has kept.
    """
    rows = (
        db.query(ScrapeJob)
        .order_by(ScrapeJob.created_at.desc(), ScrapeJob.id.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": job.id,
            "status": job.status,
            "stores": job.store_codes or "all",
            "requested_by": job.requested_by,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "result": job.result,
            "error": job.error,
        }
        for job in rows
    ]


@router.get("/price-anomalies")
async def get_price_anomalies(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """
    Products whose price moved more than 50% in 24h. Admin only.

    Usually a scrape error -- a parsing change, or a store publishing a
    placeholder -- rather than a real discount, which is why it is worth
    surfacing.

    Uses a window function so this is ONE query. The previous version ran a
    subquery per history row to find the preceding price, which is O(n) round
    trips against a table that grows with every scrape.
    """
    logger.info(
        "Admin checking price anomalies",
        extra={"admin_id": admin.id, "action": "admin_price_anomalies"},
    )

    cutoff = datetime.now(timezone.utc) - timedelta(days=1)

    previous_price = func.lag(PriceHistory.price).over(
        partition_by=PriceHistory.alias_id, order_by=PriceHistory.recorded_at
    )

    history = (
        select(
            PriceHistory.alias_id.label("alias_id"),
            PriceHistory.price.label("price"),
            PriceHistory.recorded_at.label("recorded_at"),
            previous_price.label("previous_price"),
        )
        .subquery()
    )

    rows = (
        db.query(
            Product.canonical_name.label("product"),
            Store.name.label("store"),
            history.c.previous_price,
            history.c.price,
            history.c.recorded_at,
        )
        .select_from(history)
        .join(ProductAlias, ProductAlias.id == history.c.alias_id)
        .join(Product, Product.id == ProductAlias.product_id)
        .join(Store, Store.id == ProductAlias.store_id)
        .filter(history.c.recorded_at > cutoff)
        .filter(history.c.previous_price.isnot(None))
        .filter(history.c.previous_price > 0)
        .order_by(history.c.recorded_at.desc())
        .all()
    )

    anomalies = []
    for row in rows:
        change = abs(row.price - row.previous_price) / row.previous_price * 100
        if change > 50:
            anomalies.append(
                {
                    "product": row.product,
                    # The store's NAME. This used to return alias.store_id, a
                    # raw integer under a field called "store".
                    "store": row.store,
                    "old_price": float(row.previous_price),
                    "new_price": float(row.price),
                    "change_percent": round(float(change), 2),
                    "recorded_at": row.recorded_at,
                }
            )

    return anomalies
