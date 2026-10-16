from fastapi import FastAPI, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import time

from database import engine, get_db, Base
from models import User

# Create all tables on startup.
# In production you'd use Alembic migrations instead — but for this
# project, create_all is fine and demonstrates schema management.
Base.metadata.create_all(bind=engine)

app = FastAPI(title="User Service", version="1.0.0")

# ── Prometheus Metrics ────────────────────────────────────────────────────────
# Three golden signals for any microservice:
# 1. REQUEST_COUNT  → throughput (how many requests per second)
# 2. REQUEST_LATENCY → latency (how long each request takes)
# 3. ACTIVE_REQUESTS → saturation (how many in-flight requests right now)
# Labels let us slice metrics by method, endpoint, and HTTP status.
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["service", "method", "endpoint", "status"]
)
REQUEST_LATENCY = Histogram(
    "request_duration_seconds",
    "Request duration in seconds",
    ["service", "endpoint"]
)
ACTIVE_REQUESTS = Gauge(
    "active_requests",
    "Number of active in-flight requests",
    ["service"]
)

SERVICE_NAME = "user-service"


# ── Pydantic Schemas ─────────────────────────────────────────────────────────
# Pydantic validates incoming request bodies and serializes responses.
# Separating schema (Pydantic) from model (SQLAlchemy) is a clean
# architectural boundary — the API contract is independent of the DB schema.
class UserCreate(BaseModel):
    name: str
    email: str


class UserResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: str
    name: str
    email: str
    created_at: str


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.post("/users", status_code=201)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    """
    Depends(get_db) is FastAPI's Dependency Injection.
    FastAPI calls get_db(), yields the session, passes it here,
    and guarantees cleanup after the request — even on exceptions.
    """
    ACTIVE_REQUESTS.labels(service=SERVICE_NAME).inc()
    start = time.time()
    try:
        # Check duplicate email before hitting the DB UNIQUE constraint
        # (gives a cleaner 409 instead of a raw DB IntegrityError)
        existing = db.query(User).filter(User.email == payload.email).first()
        if existing:
            REQUEST_COUNT.labels(service=SERVICE_NAME, method="POST", endpoint="/users", status="409").inc()
            raise HTTPException(status_code=409, detail="Email already registered")
        user = User(name=payload.name, email=payload.email)
        db.add(user)
        db.commit()
        db.refresh(user)
        REQUEST_COUNT.labels(service=SERVICE_NAME, method="POST", endpoint="/users", status="201").inc()
        return {"id": user.id, "name": user.name, "email": user.email, "created_at": str(user.created_at)}
    finally:
        REQUEST_LATENCY.labels(service=SERVICE_NAME, endpoint="/users").observe(time.time() - start)
        ACTIVE_REQUESTS.labels(service=SERVICE_NAME).dec()


@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    ACTIVE_REQUESTS.labels(service=SERVICE_NAME).inc()
    start = time.time()
    try:
        users = db.query(User).all()
        REQUEST_COUNT.labels(service=SERVICE_NAME, method="GET", endpoint="/users", status="200").inc()
        return [{"id": u.id, "name": u.name, "email": u.email, "created_at": str(u.created_at)} for u in users]
    finally:
        REQUEST_LATENCY.labels(service=SERVICE_NAME, endpoint="/users").observe(time.time() - start)
        ACTIVE_REQUESTS.labels(service=SERVICE_NAME).dec()


@app.get("/users/{user_id}")
def get_user(user_id: str, db: Session = Depends(get_db)):
    ACTIVE_REQUESTS.labels(service=SERVICE_NAME).inc()
    start = time.time()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            REQUEST_COUNT.labels(service=SERVICE_NAME, method="GET", endpoint="/users/{id}", status="404").inc()
            raise HTTPException(status_code=404, detail="User not found")
        REQUEST_COUNT.labels(service=SERVICE_NAME, method="GET", endpoint="/users/{id}", status="200").inc()
        return {"id": user.id, "name": user.name, "email": user.email, "created_at": str(user.created_at)}
    finally:
        REQUEST_LATENCY.labels(service=SERVICE_NAME, endpoint="/users/{id}").observe(time.time() - start)
        ACTIVE_REQUESTS.labels(service=SERVICE_NAME).dec()


@app.delete("/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db)):
    ACTIVE_REQUESTS.labels(service=SERVICE_NAME).inc()
    start = time.time()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            REQUEST_COUNT.labels(service=SERVICE_NAME, method="DELETE", endpoint="/users/{id}", status="404").inc()
            raise HTTPException(status_code=404, detail="User not found")
        db.delete(user)
        db.commit()
        REQUEST_COUNT.labels(service=SERVICE_NAME, method="DELETE", endpoint="/users/{id}", status="200").inc()
        return {"message": f"User {user_id} deleted"}
    finally:
        REQUEST_LATENCY.labels(service=SERVICE_NAME, endpoint="/users/{id}").observe(time.time() - start)
        ACTIVE_REQUESTS.labels(service=SERVICE_NAME).dec()


@app.get("/health")
def health():
    """Health endpoint used by Kubernetes liveness and readiness probes.
    
    Liveness probe: if this fails, K8s restarts the pod.
    Readiness probe: if this fails, K8s stops sending traffic to the pod.
    Both probes hit /health — a fast, lightweight endpoint.
    """
    return {"status": "healthy", "service": SERVICE_NAME}


@app.get("/metrics")
def metrics():
    """Prometheus scrapes this endpoint every 15s (configured in prometheus.yml).
    
    Prometheus uses a PULL model: it comes to us for metrics.
    This is opposite to push-based systems like StatsD.
    Pull model is better for cloud/K8s: Prometheus discovers targets
    dynamically and we don't need to know Prometheus's address.
    """
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
