"""
Core configuration settings for the Shopify authentication service.
"""
import secrets
import os
from typing import Optional, List, Literal
from pydantic import BaseSettings, validator
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    """Application settings with environment variable support."""
    
    # Application Settings
    APP_NAME: str = "Shopify Auth Service"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: Literal["development", "staging", "production"] = "development"
    
    # FastAPI Settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    RELOAD: bool = False
    
    # Security Settings
    SECRET_KEY: str = secrets.token_urlsafe(32)
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    
    # ✅ CRITICAL: Shopify Configuration - MUST be loaded from environment
    SHOPIFY_CLIENT_ID: str
    SHOPIFY_CLIENT_SECRET: str
    SHOPIFY_REDIRECT_URI: str
    SHOPIFY_SCOPES: str = "read_orders,write_products,read_customers"
    
    @validator("SHOPIFY_SCOPES")
    def parse_shopify_scopes(cls, v: str) -> List[str]:
        """Parse comma-separated scopes into a list."""
        return [scope.strip() for scope in v.split(",") if scope.strip()]
    
    # Database Configuration
    DATABASE_URL: str
    SUPABASE_URL: str = ""
    SUPABASE_ANON_KEY: str = ""
    SUPABASE_SERVICE_KEY: str = ""
    
    # Database Connection Pool Settings
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30
    DB_POOL_RECYCLE: int = 1800
    
    # Logging Configuration
    LOG_LEVEL: str = "INFO"
    
    class Config:
        env_file = ".env"
        case_sensitive = True
        
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Debug print to verify values are loaded
        if self.DEBUG:
            print(f"🔧 Config loaded:")
            print(f"   SHOPIFY_CLIENT_ID: {self.SHOPIFY_CLIENT_ID[:10]}...")
            print(f"   SHOPIFY_REDIRECT_URI: {self.SHOPIFY_REDIRECT_URI}")


# Global settings instance
settings = Settings()

# Additional verification that settings are loaded correctly
if not settings.SHOPIFY_CLIENT_ID or settings.SHOPIFY_CLIENT_ID == "test":
    raise ValueError("❌ SHOPIFY_CLIENT_ID not properly loaded from environment!")

if not settings.SHOPIFY_CLIENT_SECRET or settings.SHOPIFY_CLIENT_SECRET == "test":
    raise ValueError("❌ SHOPIFY_CLIENT_SECRET not properly loaded from environment!")

print(f"✅ Settings loaded successfully. Client ID: {settings.SHOPIFY_CLIENT_ID[:10]}...")