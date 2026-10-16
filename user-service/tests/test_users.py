import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker



from main import app
from database import Base, get_db

# ── Test Database Setup ───────────────────────────────────────────────────────
# We use SQLite in-memory for tests.
# Reasons:
# 1. No external PostgreSQL needed in CI/CD
# 2. Each test run starts with a clean, empty DB
# 3. Tests are isolated and repeatable
TEST_DB_URL = "sqlite:///./test_users.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Replace the real DB dependency with the test DB.
    
    FastAPI's dependency override mechanism lets us swap any Depends()
    function at test time — without changing production code.
    This is Dependency Injection in action: loose coupling between
    the business logic and its infrastructure (DB).
    """
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Override the dependency globally for all tests in this file
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test, drop after. Ensures isolation."""
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_create_user_success():
    """POST /users should return 201 and the created user data."""
    response = client.post("/users", json={"name": "Snehitha", "email": "snehitha@test.com"})
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Snehitha"
    assert data["email"] == "snehitha@test.com"
    assert "id" in data


def test_create_duplicate_email_fails():
    """Creating a user with an existing email should return 409."""
    client.post("/users", json={"name": "Snehitha", "email": "dup@test.com"})
    response = client.post("/users", json={"name": "Other", "email": "dup@test.com"})
    assert response.status_code == 409


def test_get_existing_user():
    """GET /users/{id} should return 200 and user data for a valid ID."""
    create_resp = client.post("/users", json={"name": "Snehitha", "email": "get@test.com"})
    user_id = create_resp.json()["id"]
    response = client.get(f"/users/{user_id}")
    assert response.status_code == 200
    assert response.json()["email"] == "get@test.com"


def test_get_nonexistent_user_returns_404():
    """GET /users/{id} should return 404 for a non-existent ID."""
    response = client.get("/users/nonexistent-id")
    assert response.status_code == 404


def test_delete_user():
    """DELETE /users/{id} should return 200 and remove the user."""
    create_resp = client.post("/users", json={"name": "Del", "email": "del@test.com"})
    user_id = create_resp.json()["id"]
    delete_resp = client.delete(f"/users/{user_id}")
    assert delete_resp.status_code == 200
    # Verify it's actually gone
    get_resp = client.get(f"/users/{user_id}")
    assert get_resp.status_code == 404


def test_health_endpoint():
    """GET /health should return 200 and healthy status."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
