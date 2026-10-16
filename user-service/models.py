import uuid
from datetime import datetime
from sqlalchemy import Column, String, DateTime
from database import Base


class User(Base):
    """SQLAlchemy ORM model for users.
    
    ORM (Object-Relational Mapper): maps Python classes to DB tables.
    Instead of writing raw SQL, we interact with Python objects.
    SQLAlchemy translates these to SQL at runtime.
    """
    __tablename__ = "users"

    # UUID as primary key is a best practice in distributed systems:
    # - No central sequence/auto-increment needed
    # - Safe to generate on the client side
    # - No ID collision across microservices or DB shards
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name = Column(String, nullable=False)
    # unique=True creates a DB-level UNIQUE constraint — prevents duplicates
    # even under concurrent inserts (DB enforces this, not just app logic)
    email = Column(String, unique=True, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
