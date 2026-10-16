# CQRS Pattern: This FastAPI app is the READ side.
# It only reads notifications from PostgreSQL.
# The WRITE side is worker.py — a separate process that consumes
# from the Redis queue and inserts notification records.
#
# Why separate READ and WRITE?
# - They can scale independently
# - Read-heavy workloads can have many API replicas; worker replicas handle write throughput
# - Failure in the worker doesn't crash the read API

import time
from fastapi import FastAPI, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

from database import engine, get_db, Base
from models import Notification

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Notification Service", version="1.0.0")

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests", ["service", "method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("request_duration_seconds", "Request duration", ["service", "endpoint"])
ACTIVE_REQUESTS = Gauge("active_requests", "Active in-flight requests", ["service"])
SERVICE_NAME = "notification-service"


@app.get("/notifications")
def list_notifications(db: Session = Depends(get_db)):
    ACTIVE_REQUESTS.labels(service=SERVICE_NAME).inc()
    start = time.time()
    try:
        notifs = db.query(Notification).order_by(Notification.created_at.desc()).all()
        REQUEST_COUNT.labels(service=SERVICE_NAME, method="GET", endpoint="/notifications", status="200").inc()
        return [
            {
                "id": n.id,
                "order_id": n.order_id,
                "user_id": n.user_id,
                "message": n.message,
                "status": n.status,
                "created_at": str(n.created_at)
            }
            for n in notifs
        ]
    finally:
        REQUEST_LATENCY.labels(service=SERVICE_NAME, endpoint="/notifications").observe(time.time() - start)
        ACTIVE_REQUESTS.labels(service=SERVICE_NAME).dec()


@app.get("/notifications/{notification_id}")
def get_notification(notification_id: str, db: Session = Depends(get_db)):
    ACTIVE_REQUESTS.labels(service=SERVICE_NAME).inc()
    start = time.time()
    try:
        notif = db.query(Notification).filter(Notification.id == notification_id).first()
        if not notif:
            REQUEST_COUNT.labels(service=SERVICE_NAME, method="GET", endpoint="/notifications/{id}", status="404").inc()
            raise HTTPException(status_code=404, detail="Notification not found")
        REQUEST_COUNT.labels(service=SERVICE_NAME, method="GET", endpoint="/notifications/{id}", status="200").inc()
        return {
            "id": notif.id,
            "order_id": notif.order_id,
            "user_id": notif.user_id,
            "message": notif.message,
            "status": notif.status
        }
    finally:
        REQUEST_LATENCY.labels(service=SERVICE_NAME, endpoint="/notifications/{id}").observe(time.time() - start)
        ACTIVE_REQUESTS.labels(service=SERVICE_NAME).dec()


@app.get("/health")
def health():
    return {"status": "healthy", "service": SERVICE_NAME}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
