from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings

settings = get_settings()

# SQLite is only ever a LOCAL/dev database (the test suite uses it, and it lets
# the app boot without Postgres). It needs different engine arguments from a
# server database: a file connection is bound to the thread that opened it, so
# a threaded server -- uvicorn offloads sync endpoints to a threadpool --
# hits "SQLite objects created in a thread can only be used in that same
# thread" unless check_same_thread is off, and QueuePool's size knobs do not
# apply. Production is Postgres and takes the branch below untouched.
if settings.database_url.startswith("sqlite"):
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
else:
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()