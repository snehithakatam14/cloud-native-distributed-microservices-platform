import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime
from database import Base


class Notification(Base):
    """Represents a notification triggered by an order_created event.
    
    Written by the worker (WRITE side), read by the API (READ side).
    This separation is a simplified form of CQRS (Command Query Responsibility Segregation):
    - Commands (writes) go through worker.py, which consumes from Redis
    - Queries (reads) go through the FastAPI app in main.py
    CQRS lets each side scale independently and optimise for its workload.
    """
    __tablename__ = "notifications"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(String, nullable=False, index=True)
    user_id = Column(String, nullable=False)
    message = Column(String, nullable=False)
    # 'sent' is the default because the worker only writes after processing.
    # In a more complex system, you'd have 'queued' → 'sent' → 'delivered'.
    status = Column(String, default="sent")
    created_at = Column(DateTime, default=datetime.utcnow)
