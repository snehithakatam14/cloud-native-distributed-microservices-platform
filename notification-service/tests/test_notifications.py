import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


from main import app
from database import Base, get_db
from models import Notification

TEST_DB_URL = "sqlite:///./test_notifications.db"
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
    # Seed a test notification directly via the DB session.
    # We bypass the worker here because unit tests should test the API
    # in isolation — the worker is tested separately.
    db = TestingSessionLocal()
    notif = Notification(
        id="test-notif-id",
        order_id="order-123",
        user_id="user-456",
        message="Order 'Test' was created successfully.",
        status="sent"
    )
    db.add(notif)
    db.commit()
    db.close()
    yield
    Base.metadata.drop_all(bind=engine)


client = TestClient(app)


def test_list_notifications():
    response = client.get("/notifications")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert len(response.json()) == 1


def test_get_notification_by_id():
    response = client.get("/notifications/test-notif-id")
    assert response.status_code == 200
    assert response.json()["order_id"] == "order-123"


def test_get_nonexistent_notification():
    response = client.get("/notifications/does-not-exist")
    assert response.status_code == 404


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
