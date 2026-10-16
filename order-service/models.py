import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime, Text
from database import Base


class Order(Base):
    """ORM model representing a task/job submitted by a user.
    
    In a real IBM Systems context, this would represent a compute job,
    a storage provisioning request, or a cloud resource allocation.
    """
    __tablename__ = "orders"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    # user_id is a conceptual foreign key — we don't enforce it at the DB level.
    # In microservices, cross-service foreign key constraints couple services
    # together: deleting a user would require coordinating with the Order DB.
    # Instead, we keep it as a plain string reference (loose coupling).
    user_id = Column(String, nullable=False, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    # Status follows a state machine: pending → processing → done
    # This pattern is used in IBM job schedulers and cloud task systems
    status = Column(String, default="pending", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
