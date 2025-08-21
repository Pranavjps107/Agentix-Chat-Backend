"""
Authentication-related database models and Pydantic schemas.
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from sqlalchemy.sql import func
from pydantic import BaseModel, validator
from app.models.database import Base


class ShopifyAuth(Base):
    """SQLAlchemy model for storing Shopify authentication data."""
    
    __tablename__ = "shopify_auth"
    
    id = Column(Integer, primary_key=True, index=True)
    shop_domain = Column(String(255), unique=True, index=True, nullable=False)
    access_token = Column(Text, nullable=False)
    scopes = Column(Text, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Pydantic Models for API
class ShopifyAuthRequest(BaseModel):
    """Request model for initiating Shopify OAuth."""
    
    shop: str
    
    @validator("shop")
    def validate_shop_domain(cls, v: str) -> str:
        """Validate and normalize shop domain."""
        # Remove protocol and trailing slashes
        shop = v.replace("https://", "").replace("http://", "").strip("/")
        
        # Add .myshopify.com if not present
        if not shop.endswith(".myshopify.com"):
            shop = f"{shop}.myshopify.com"
        
        return shop


class ShopifyAuthCallback(BaseModel):
    """Model for handling OAuth callback."""
    
    code: str
    shop: str
    state: Optional[str] = None
    hmac: Optional[str] = None
    timestamp: Optional[str] = None


class AuthTokenResponse(BaseModel):
    """Response model for successful authentication."""
    
    access_token: str
    shop_domain: str
    scopes: List[str]
    created_at: datetime


class AuthStatusResponse(BaseModel):
    """Response model for authentication status."""
    
    is_authenticated: bool
    shop_domain: Optional[str] = None
    scopes: Optional[List[str]] = None
    last_updated: Optional[datetime] = None


class ErrorResponse(BaseModel):
    """Standard error response model."""
    
    error: str
    detail: Optional[str] = None
    code: Optional[str] = None