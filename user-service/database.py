import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# DATABASE_URL is injected via Kubernetes ConfigMap or .env file
# In production (K8s), this is never hardcoded — it comes from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./test.db")

# create_engine sets up the connection pool.
# Connection pooling reuses DB connections instead of creating a new TCP
# connection per request — critical for high-throughput microservices.
# For SQLite (testing), connect_args allows multi-threaded access.
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

# SessionLocal is a factory: each request gets its own DB session
# autocommit=False means we must explicitly commit transactions
# autoflush=False prevents automatic SQL emission before queries
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all ORM models — each model class inherits from Base
Base = declarative_base()


def get_db():
    """FastAPI dependency that provides a DB session per request.
    
    Using 'yield' makes this a context manager:
    - DB session is created before the request handler runs
    - Session is always closed after (even if the handler raises an exception)
    This prevents connection leaks — a common source of production outages.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
