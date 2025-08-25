# scripts/setup_database.py
"""
Database setup script for Shopify data tables.
"""
import sys
import os

# Add the parent directory to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.database import engine, Base
from app.models.auth import ShopifyAuth
from app.models.shopify_data import *
from app.core.logging import setup_logging, logger

def create_tables():
    """Create all database tables."""
    try:
        setup_logging()
        logger.info("🔧 Setting up database tables...")
        
        # Create all tables
        Base.metadata.create_all(bind=engine)
        
        logger.info("✅ Database tables created successfully!")
        logger.info("Created tables:")
        for table_name in Base.metadata.tables.keys():
            logger.info(f"  - {table_name}")
        
    except Exception as e:
        logger.error(f"❌ Error creating tables: {str(e)}")
        raise

if __name__ == "__main__":
    create_tables()