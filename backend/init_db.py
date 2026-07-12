from app.database import engine, Base
from app.models import Stock, Fundamentals, PriceHistory, Portfolio
import os

def init_db():
    """Create all tables on startup"""
    Base.metadata.create_all(bind=engine)
    print("Database initialized")

if __name__ == "__main__":
    init_db()
