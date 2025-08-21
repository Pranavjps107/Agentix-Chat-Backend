"""Pytest configuration and fixtures."""
import pytest
import asyncio
from typing import AsyncGenerator, Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from httpx import AsyncClient
from app.main import app
from app.models.database import Base, get_db
from app.core.config import settings

# Test database URL (use SQLite for testing)
TEST_DATABASE_URL = "sqlite:///./test.db"

# Create test engine
engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    """Override database dependency for testing."""
    try:
        db = TestingSessionLocal()
        yield db
    finally:
        db.close()


# Override dependency
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def db_session():
    """Create a database session for testing."""
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        # Drop tables after each test
        Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="function")
def client() -> Generator[TestClient, None, None]:
    """Create a test client."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="function")
async def async_client() -> AsyncGenerator[AsyncClient, None]:
    """Create an async test client."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_shop_domain() -> str:
    """Sample shop domain for testing."""
    return "test-shop.myshopify.com"


@pytest.fixture
def sample_auth_request():
    """Sample authentication request data."""
    return {"shop": "test-shop"}


@pytest.fixture
def sample_callback_params():
    """Sample callback parameters."""
    return {
        "code": "test-code-12345",
        "shop": "test-shop.myshopify.com",
        "state": "test-state-67890",
        "timestamp": "1234567890"
    }


@pytest.fixture
def sample_token_response():
    """Sample token response from Shopify."""
    return {
        "access_token": "shpat_test_token_12345",
        "scope": "read_orders,write_products"
    }