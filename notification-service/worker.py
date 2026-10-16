import os
import json
import time
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import redis

# Configure structured logging — in production, this feeds into
# centralized log aggregation systems (ELK stack, IBM Log Analysis)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from models import Notification
from database import Base

# ── Database Setup ─────────────────────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./worker.db")
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

# ── Redis Setup ────────────────────────────────────────────────────────────────
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


def process_event(event_data: dict):
    """Write a Notification record to the database.
    
    This is the WRITE side of CQRS — the worker is the only process
    that inserts into the notifications table. The FastAPI app only reads.
    """
    db = SessionLocal()
    try:
        notification = Notification(
            order_id=event_data.get("order_id", ""),
            user_id=event_data.get("user_id", ""),
            message=f"Order '{event_data.get('title', '')}' was created successfully.",
            status="sent"
        )
        db.add(notification)
        db.commit()
        logger.info(f"Notification saved for order {event_data.get('order_id')}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to save notification: {e}")
    finally:
        db.close()


def main():
    """
    The main worker loop.

    BRPOP (Blocking Right POP):
    - Waits for an item in the Redis list 'notifications'
    - Blocks until an item is available (no busy-waiting / CPU spinning)
    - timeout=5 means: if no message for 5 seconds, return None and loop again
    - Why timeout? Allows the loop to check a shutdown flag or log a heartbeat.
      Without timeout, BRPOP blocks forever — can't gracefully shut down.

    Why an infinite loop?
    - Workers are long-lived processes, always listening for new events
    - Kubernetes ensures the pod restarts if it crashes (restartPolicy: Always)

    Producer-Consumer Pattern:
    - Order Service (Producer) pushes events to Redis LIST
    - This Worker (Consumer) pops and processes them
    - Benefit: Order Service response time is NOT affected by notification processing
    - If we had 100 orders/second, notifications process in the background
      without slowing down the order creation API

    Durability caveat:
    - Simple Redis LISTs lose messages if the worker crashes mid-processing
    - Production solution: use Redis Streams (XADD/XREADGROUP) or Apache Kafka
      which support consumer groups and message acknowledgment
    """
    logger.info(f"Notification worker starting. Listening on Redis {REDIS_HOST}:{REDIS_PORT}")

    while True:
        try:
            # BRPOP returns (list_name, value) or None on timeout
            result = redis_client.brpop("notifications", timeout=5)

            if result is None:
                # Timeout — no messages. Log heartbeat and continue listening.
                logger.debug("No messages, still listening...")
                continue

            _, raw_message = result
            event = json.loads(raw_message)
            logger.info(f"Received event: {event.get('event')} for order {event.get('order_id')}")
            process_event(event)

        except redis.ConnectionError as e:
            # Redis went down — wait and retry (resilience pattern)
            logger.error(f"Redis connection error: {e}. Retrying in 5s...")
            time.sleep(5)
        except json.JSONDecodeError as e:
            # Malformed message — log and skip (poison pill handling)
            logger.error(f"Invalid JSON in queue: {e}")
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            time.sleep(1)


if __name__ == "__main__":
    main()
