import os
import json
import time
from fastapi import FastAPI, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from pydantic import BaseModel
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import redis

from database import engine, get_db, Base
from models import Order

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Order Service", version="1.0.0")

# ── Redis Connection ──────────────────────────────────────────────────────────
# Redis is used as a message broker here.
# When an order is created, we push a notification event to a Redis LIST.
# The Notification Worker (a separate process/pod) reads from this list.
# This decouples the Order Service from the Notification Service:
# - Order creation is fast (just DB write + Redis push)
# - Notification sending happens asynchronously in a separate process
# - If Notification Service is down, orders still succeed (fault isolation)
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))

try:
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
except Exception:
    redis_client = None

# ── Prometheus Metrics ─────────────────────────────────────────────────────────
REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["service", "method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("request_duration_seconds", "Request duration", ["service", "endpoint"])
ACTIVE_REQUESTS = Gauge("active_requests", "Active in-flight requests", ["service"])
SERVICE_NAME = "order-service"


# ── Pydantic Schemas ──────────────────────────────────────────────────────────
class OrderCreate(BaseModel):
    user_id: str
    title: str
    description: str = ""


class StatusUpdate(BaseModel):
    status: str


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.post("/orders", status_code=201)
def create_order(payload: OrderCreate, db: Session = Depends(get_db)):
    ACTIVE_REQUESTS.labels(service=SERVICE_NAME).inc()
    start = time.time()
    try:
        order = Order(
            user_id=payload.user_id,
            title=payload.title,
            description=payload.description,
            status="pending"
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        # Push event to Redis LIST named 'notifications'
        # LPUSH adds to the LEFT (head) of the list
        # The worker does BRPOP from the RIGHT (tail) — FIFO queue
        # This is the Producer side of the Producer-Consumer pattern.
        # Benefit: Order Service doesn't wait for notification to be sent.
        # The order succeeds in ~5ms; notification is sent asynchronously.
        event = {
            "event": "order_created",
            "order_id": order.id,
            "user_id": order.user_id,
            "title": order.title
        }
        if redis_client:
            redis_client.lpush("notifications", json.dumps(event))

        REQUEST_COUNT.labels(service=SERVICE_NAME, method="POST", endpoint="/orders", status="201").inc()
        return {
            "id": order.id,
            "user_id": order.user_id,
            "title": order.title,
            "description": order.description,
            "status": order.status,
            "created_at": str(order.created_at)
        }
    finally:
        REQUEST_LATENCY.labels(service=SERVICE_NAME, endpoint="/orders").observe(time.time() - start)
        ACTIVE_REQUESTS.labels(service=SERVICE_NAME).dec()


@app.get("/orders")
def list_orders(db: Session = Depends(get_db)):
    ACTIVE_REQUESTS.labels(service=SERVICE_NAME).inc()
    start = time.time()
    try:
        orders = db.query(Order).all()
        REQUEST_COUNT.labels(service=SERVICE_NAME, method="GET", endpoint="/orders", status="200").inc()
        return [
            {"id": o.id, "user_id": o.user_id, "title": o.title, "status": o.status, "created_at": str(o.created_at)}
            for o in orders
        ]
    finally:
        REQUEST_LATENCY.labels(service=SERVICE_NAME, endpoint="/orders").observe(time.time() - start)
        ACTIVE_REQUESTS.labels(service=SERVICE_NAME).dec()


@app.get("/orders/{order_id}")
def get_order(order_id: str, db: Session = Depends(get_db)):
    ACTIVE_REQUESTS.labels(service=SERVICE_NAME).inc()
    start = time.time()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            REQUEST_COUNT.labels(service=SERVICE_NAME, method="GET", endpoint="/orders/{id}", status="404").inc()
            raise HTTPException(status_code=404, detail="Order not found")
        REQUEST_COUNT.labels(service=SERVICE_NAME, method="GET", endpoint="/orders/{id}", status="200").inc()
        return {
            "id": order.id,
            "user_id": order.user_id,
            "title": order.title,
            "status": order.status,
            "created_at": str(order.created_at)
        }
    finally:
        REQUEST_LATENCY.labels(service=SERVICE_NAME, endpoint="/orders/{id}").observe(time.time() - start)
        ACTIVE_REQUESTS.labels(service=SERVICE_NAME).dec()


@app.patch("/orders/{order_id}/status")
def update_status(order_id: str, payload: StatusUpdate, db: Session = Depends(get_db)):
    ACTIVE_REQUESTS.labels(service=SERVICE_NAME).inc()
    start = time.time()
    try:
        order = db.query(Order).filter(Order.id == order_id).first()
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        valid_statuses = ["pending", "processing", "done"]
        if payload.status not in valid_statuses:
            raise HTTPException(status_code=400, detail=f"Status must be one of {valid_statuses}")
        order.status = payload.status
        db.commit()
        db.refresh(order)
        REQUEST_COUNT.labels(service=SERVICE_NAME, method="PATCH", endpoint="/orders/{id}/status", status="200").inc()
        return {"id": order.id, "status": order.status}
    finally:
        REQUEST_LATENCY.labels(service=SERVICE_NAME, endpoint="/orders/{id}/status").observe(time.time() - start)
        ACTIVE_REQUESTS.labels(service=SERVICE_NAME).dec()


@app.get("/health")
def health():
    return {"status": "healthy", "service": SERVICE_NAME}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
