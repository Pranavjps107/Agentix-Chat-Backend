"""
Database configuration and connection management optimized for Supabase.
"""
from sqlalchemy import create_engine, MetaData, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import QueuePool
from app.core.config import settings
from app.core.logging import logger
import time

# Create database engine with Supabase-optimized settings
engine = create_engine(
    str(settings.DATABASE_URL),
    poolclass=QueuePool,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=True,  # Validates connections before use
    echo=settings.DEBUG,  # Log SQL queries in debug mode
    connect_args={
        "connect_timeout": 10,
        "application_name": settings.APP_NAME,
    }
)

# Add connection event listeners for monitoring
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    """Set connection parameters when connecting to PostgreSQL."""
    if settings.DEBUG:
        logger.info("New database connection established")

@event.listens_for(engine, "checkout")
def receive_checkout(dbapi_connection, connection_record, connection_proxy):
    """Log when a connection is checked out from the pool."""
    if settings.DEBUG:
        logger.debug("Connection checked out from pool")

@event.listens_for(engine, "checkin")
def receive_checkin(dbapi_connection, connection_record):
    """Log when a connection is returned to the pool."""
    if settings.DEBUG:
        logger.debug("Connection returned to pool")

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create base class for models
Base = declarative_base()

# Metadata for migrations
metadata = MetaData()


def get_db():
    """
    Dependency for getting database session with proper error handling.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Database session error: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


def test_database_connection() -> bool:
    """
    Test database connectivity.
    
    Returns:
        True if connection successful, False otherwise
    """
    try:
        with engine.connect() as connection:
            connection.execute("SELECT 1")
        logger.info("Database connection test successful")
        return True
    except Exception as e:
        logger.error(f"Database connection test failed: {str(e)}")
        return False


def get_connection_pool_status():
    """Get current connection pool status for monitoring."""
    pool = engine.pool
    return {
        "pool_size": pool.size(),
        "checked_in": pool.checkedin(),
        "checked_out": pool.checkedout(),
        "overflow": pool.overflow(),
        "invalid": pool.invalid()
    }