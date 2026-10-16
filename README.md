# Cloud-Native Distributed Microservices Platform

> **IBM Systems & Cloud Software Engineer Portfolio Project**  
> Python · FastAPI · Docker · Kubernetes · Redis · PostgreSQL · Prometheus · Grafana · GitHub Actions

---

## Architecture

```
                        ┌─────────────────────┐
                        │     Client / curl   │
                        └──────────┬──────────┘
                                   │ HTTP :8000
                                   ▼
                        ┌─────────────────────┐
                        │     API Gateway     │  ← Single entry point
                        │  (FastAPI + httpx)  │    Routes all traffic
                        └──┬──────┬───────┬───┘
              /api/users   │      │       │  /api/notifications
                           │      │       │
              ┌────────────▼─┐  ┌─▼──────────┐  ┌────────────────────┐
              │ User Service │  │Order Service│  │Notification Service│
              │  (FastAPI)   │  │  (FastAPI)  │  │    (FastAPI)       │
              │   Port 8001  │  │  Port 8002  │  │    Port 8003       │
              └──────┬───────┘  └──┬──────┬───┘  └────────┬───────────┘
                     │             │      │                │
                     └─────────────┘      │                │
                            │             │ LPUSH          │ BRPOP (reads)
                            ▼             ▼                │
                      ┌──────────┐   ┌─────────┐          │
                      │PostgreSQL│   │  Redis  │◄──────────┘
                      │  :5432   │   │  :6379  │
                      └──────────┘   └────┬────┘
                                          │ BRPOP (worker consumes)
                                          ▼
                                ┌──────────────────┐
                                │Notification Worker│  ← Async consumer
                                │  (Python script) │    Writes to Postgres
                                └──────────────────┘

All services → /metrics → Prometheus (:9090) → Grafana (:3000)
```

---

## Tech Stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python 3.11 | Core language for all services |
| API Framework | FastAPI | REST APIs, async support, auto OpenAPI docs |
| Database | PostgreSQL 15 | Persistent relational storage |
| Messaging / Cache | Redis 7 | Async event queue (LPUSH/BRPOP pattern) |
| Containers | Docker | Service isolation and packaging |
| Orchestration | Kubernetes | Deployment, scaling, self-healing |
| Local K8s | Minikube | Kubernetes cluster on local machine |
| Observability | Prometheus + Grafana | Metrics scraping and dashboards |
| CI/CD | GitHub Actions | Automated testing and build pipeline |
| Testing | PyTest | Unit and integration tests |

---

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (with Docker engine running)
- [Minikube](https://minikube.sigs.k8s.io/docs/start/) (`choco install minikube` or brew)
- [kubectl](https://kubernetes.io/docs/tasks/tools/) (`choco install kubernetes-cli`)
- Python 3.11+

---

## Quick Start — Local (Docker Compose)

```bash
# Clone the repo
git clone https://github.com/snehithakatam14/cloud-platform.git
cd cloud-platform

# Start all 9 services (PostgreSQL, Redis, 3 microservices, worker, gateway, Prometheus, Grafana)
docker-compose up --build

# Verify all containers are running
docker ps
```

**Service URLs after startup:**

| Service | URL |
|---|---|
| API Gateway | http://localhost:8000 |
| User Service | http://localhost:8001/docs |
| Order Service | http://localhost:8002/docs |
| Notification Service | http://localhost:8003/docs |
| Prometheus | http://localhost:9090 |
| Grafana | http://localhost:3000 (admin/admin) |

---

## Quick Start — Kubernetes (Minikube)

```bash
# 1. Start Minikube
minikube start --cpus=4 --memory=4096

# 2. Point Docker CLI to Minikube's Docker daemon
# (builds go directly into Minikube — no registry needed)
eval $(minikube docker-env)           # Linux/macOS
# OR on Windows PowerShell:
# & minikube -p minikube docker-env --shell powershell | Invoke-Expression

# 3. Build all Docker images inside Minikube
docker build -t cloud-platform/user-service:latest ./user-service
docker build -t cloud-platform/order-service:latest ./order-service
docker build -t cloud-platform/notification-api:latest -f ./notification-service/Dockerfile.api ./notification-service
docker build -t cloud-platform/notification-worker:latest -f ./notification-service/Dockerfile.worker ./notification-service
docker build -t cloud-platform/api-gateway:latest ./api-gateway

# 4. Deploy to Kubernetes
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/configmap.yaml
kubectl apply -f k8s/secret.yaml
kubectl apply -f k8s/postgres/pvc.yaml
kubectl apply -f k8s/postgres/deployment.yaml
kubectl apply -f k8s/redis/deployment.yaml
kubectl apply -f k8s/user-service/deployment.yaml
kubectl apply -f k8s/order-service/deployment.yaml
kubectl apply -f k8s/notification-service/deployment.yaml
kubectl apply -f k8s/api-gateway/deployment.yaml

# 5. Watch pods come up
kubectl get pods -n cloud-platform -w

# 6. Access the gateway
minikube service api-gateway -n cloud-platform --url
# OR directly: http://$(minikube ip):30000
```

---

## API Endpoints

### Via API Gateway (port 8000)

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/users` | Create a user |
| `GET` | `/api/users` | List all users |
| `GET` | `/api/users/{id}` | Get user by ID |
| `DELETE` | `/api/users/{id}` | Delete user |
| `POST` | `/api/orders` | Create order (triggers async notification) |
| `GET` | `/api/orders` | List all orders |
| `GET` | `/api/orders/{id}` | Get order by ID |
| `PATCH` | `/api/orders/{id}/status` | Update order status |
| `GET` | `/api/notifications` | List all notifications |
| `GET` | `/health` | Gateway + all services health check |

### Example Requests

```bash
# Create a user
curl -X POST http://localhost:8000/api/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Snehitha", "email": "snehitha@example.com"}'

# Create an order (this pushes to Redis → worker creates a notification)
curl -X POST http://localhost:8000/api/orders \
  -H "Content-Type: application/json" \
  -d '{"user_id": "<user-id>", "title": "My First Order", "description": "Test"}'

# Check notifications (created async by the worker)
curl http://localhost:8000/api/notifications
```

---

## Running Tests

```bash
# Run all tests for a service
cd user-service && pytest tests/ -v

# Run all services
pytest user-service/tests/ order-service/tests/ notification-service/tests/ -v

# With coverage
pip install pytest-cov
pytest user-service/tests/ --cov=. --cov-report=term-missing
```

---

## Verifying Kubernetes Features

```bash
# Check all pods running with 2 replicas
kubectl get pods -n cloud-platform

# Check HPA status (order-service autoscaler)
kubectl get hpa -n cloud-platform

# Watch rolling update in action
kubectl set image deployment/user-service user-service=cloud-platform/user-service:v2 -n cloud-platform
kubectl rollout status deployment/user-service -n cloud-platform

# Check resource usage
kubectl top pods -n cloud-platform

# View logs
kubectl logs -l app=order-service -n cloud-platform --tail=50
kubectl logs -l app=notification-worker -n cloud-platform --tail=50
```

---

## Monitoring

**Prometheus** — http://localhost:9090
- Query: `rate(http_requests_total[5m])` → per-service request rate
- Query: `histogram_quantile(0.95, rate(request_duration_seconds_bucket[5m]))` → P95 latency

**Grafana** — http://localhost:3000 (admin/admin)
1. Add data source: Prometheus → URL: `http://prometheus:9090`
2. Create dashboard with panels for request rate, P95 latency, active requests, error rate

---

## Key Concepts (Interview Reference)

| Concept | Where it's demonstrated |
|---|---|
| **Microservices** | 3 independent services + 1 worker, each with its own codebase |
| **Containerization** | Dockerfile per service, Docker Compose for local dev |
| **Kubernetes Orchestration** | Deployments, Services, ConfigMaps, Secrets, Namespace |
| **High Availability (HA)** | replicas: 2 for user-service and order-service |
| **RAS — Reliability** | Rolling updates with maxUnavailable: 0 (zero-downtime deploys) |
| **RAS — Availability** | Liveness probes restart dead pods; replicas absorb failures |
| **RAS — Serviceability** | Readiness probes gate traffic; structured logs; Prometheus alerts |
| **Horizontal Scaling** | HPA on order-service: 2→5 replicas based on CPU |
| **Async I/O / Decoupling** | Redis LPUSH (order-service) + BRPOP (notification-worker) |
| **Observability** | Prometheus metrics (/metrics) + Grafana dashboards |
| **CI/CD** | GitHub Actions: test → lint → build on every push |
| **Dependency Injection** | FastAPI Depends(get_db) for DB session management |
| **Event-Driven Architecture** | Producer-Consumer pattern via Redis queue |

<!-- trigger ci -->
