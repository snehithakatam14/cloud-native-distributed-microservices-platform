# Cloud-Native Distributed Microservices Platform  
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

## Key Concepts

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

