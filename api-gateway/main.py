"""
API Gateway — Single Entry Point for the Platform

In a microservices architecture, the API Gateway is the front door.
All client traffic hits the gateway, which routes to the appropriate service.

Benefits:
- Clients don't need to know individual service addresses (service discovery)
- Cross-cutting concerns (auth, rate limiting, logging) can live here
- Services can change ports/hosts without affecting clients

In Kubernetes, service-to-service communication uses DNS:
  http://user-service:8001  →  K8s resolves 'user-service' to the ClusterIP
This works because K8s creates a DNS record for every Service object.
"""

import os
import time
import httpx
from fastapi import FastAPI, Request, Response
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

app = FastAPI(title="API Gateway", version="1.0.0")

# Service URLs from environment (injected by K8s ConfigMap)
USER_SERVICE_URL = os.getenv("USER_SERVICE_URL", "http://localhost:8001")
ORDER_SERVICE_URL = os.getenv("ORDER_SERVICE_URL", "http://localhost:8002")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8003")

REQUEST_COUNT = Counter("gateway_requests_total", "Gateway total requests", ["method", "path", "status"])
REQUEST_LATENCY = Histogram("gateway_request_duration_seconds", "Gateway request duration", ["path"])


async def forward_request(request: Request, target_url: str) -> Response:
    """Forward an HTTP request to a downstream service.
    
    Uses httpx.AsyncClient for async, non-blocking HTTP.
    This is critical: if we used synchronous requests, each forwarded call
    would block a thread — under load, we'd run out of threads fast.
    httpx async means we can handle thousands of concurrent forwards.
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        method = request.method
        headers = dict(request.headers)
        # Remove 'host' header so the downstream service sees its own hostname,
        # not the gateway's. Failing to strip this causes routing errors in
        # virtual-host-based servers.
        headers.pop("host", None)
        body = await request.body()

        response = await client.request(
            method=method,
            url=target_url,
            headers=headers,
            content=body,
            params=dict(request.query_params)
        )
        return Response(
            content=response.content,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.headers.get("content-type")
        )


@app.api_route("/api/users/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_user_service(path: str, request: Request):
    start = time.time()
    # Build the downstream URL: path may be empty (list) or an ID (detail)
    target = f"{USER_SERVICE_URL}/users/{path}" if path else f"{USER_SERVICE_URL}/users"
    try:
        response = await forward_request(request, target)
        REQUEST_COUNT.labels(method=request.method, path="/api/users", status=str(response.status_code)).inc()
        return response
    finally:
        REQUEST_LATENCY.labels(path="/api/users").observe(time.time() - start)


@app.api_route("/api/orders/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_order_service(path: str, request: Request):
    start = time.time()
    target = f"{ORDER_SERVICE_URL}/orders/{path}" if path else f"{ORDER_SERVICE_URL}/orders"
    try:
        response = await forward_request(request, target)
        REQUEST_COUNT.labels(method=request.method, path="/api/orders", status=str(response.status_code)).inc()
        return response
    finally:
        REQUEST_LATENCY.labels(path="/api/orders").observe(time.time() - start)


@app.api_route("/api/notifications/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy_notification_service(path: str, request: Request):
    start = time.time()
    target = f"{NOTIFICATION_SERVICE_URL}/notifications/{path}" if path else f"{NOTIFICATION_SERVICE_URL}/notifications"
    try:
        response = await forward_request(request, target)
        REQUEST_COUNT.labels(method=request.method, path="/api/notifications", status=str(response.status_code)).inc()
        return response
    finally:
        REQUEST_LATENCY.labels(path="/api/notifications").observe(time.time() - start)


@app.get("/health")
async def health():
    """Aggregate health check — calls /health on all downstream services.
    
    Returns overall platform status and per-service status.
    K8s readiness probe hits this endpoint: if any service is 'unreachable',
    the gateway pod is marked 'Not Ready' and removed from the load balancer.
    """
    services = {
        "user-service": f"{USER_SERVICE_URL}/health",
        "order-service": f"{ORDER_SERVICE_URL}/health",
        "notification-service": f"{NOTIFICATION_SERVICE_URL}/health",
    }
    results = {}
    async with httpx.AsyncClient(timeout=5.0) as client:
        for name, url in services.items():
            try:
                resp = await client.get(url)
                results[name] = "healthy" if resp.status_code == 200 else "unhealthy"
            except Exception:
                results[name] = "unreachable"

    overall = "healthy" if all(v == "healthy" for v in results.values()) else "degraded"
    return {"status": overall, "gateway": "healthy", "services": results}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/")
async def root():
    return {
        "service": "API Gateway",
        "routes": ["/api/users", "/api/orders", "/api/notifications"],
        "health": "/health",
        "metrics": "/metrics"
    }
