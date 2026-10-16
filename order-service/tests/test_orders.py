import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker



from main import app
from database import Base, get_db

TEST_DB_URL = "sqlite:///./test_orders.db"
engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


@patch("main.redis_client")
def test_create_order_success(mock_redis):
    """Mock Redis so tests don't need a real Redis instance.
    
    Mocking external dependencies (Redis, external APIs) in unit tests
    is a best practice: tests should only test YOUR code, not the
    behavior of external systems. This makes tests fast and reliable.
    """
    mock_redis.lpush = MagicMock(return_value=1)
    response = client.post("/orders", json={
        "user_id": "user-123",
        "title": "Test Order",
        "description": "A test order"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Order"
    assert data["status"] == "pending"
    assert "id" in data
    # Verify Redis push was called — the async event was dispatched
    mock_redis.lpush.assert_called_once()


@patch("main.redis_client")
def test_get_order(mock_redis):
    mock_redis.lpush = MagicMock(return_value=1)
    create_resp = client.post("/orders", json={"user_id": "u1", "title": "Order A"})
    order_id = create_resp.json()["id"]
    response = client.get(f"/orders/{order_id}")
    assert response.status_code == 200
    assert response.json()["title"] == "Order A"


@patch("main.redis_client")
def test_update_order_status(mock_redis):
    mock_redis.lpush = MagicMock(return_value=1)
    create_resp = client.post("/orders", json={"user_id": "u1", "title": "Order B"})
    order_id = create_resp.json()["id"]
    response = client.patch(f"/orders/{order_id}/status", json={"status": "processing"})
    assert response.status_code == 200
    assert response.json()["status"] == "processing"


@patch("main.redis_client")
def test_get_nonexistent_order(mock_redis):
    response = client.get("/orders/does-not-exist")
    assert response.status_code == 404


@patch("main.redis_client")
def test_invalid_status_rejected(mock_redis):
    mock_redis.lpush = MagicMock(return_value=1)
    create_resp = client.post("/orders", json={"user_id": "u1", "title": "Order C"})
    order_id = create_resp.json()["id"]
    response = client.patch(f"/orders/{order_id}/status", json={"status": "invalid-status"})
    assert response.status_code == 400
