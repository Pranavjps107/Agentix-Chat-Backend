"""
Health check endpoints for monitoring database and service status.
"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.models.database import get_db, test_database_connection, get_connection_pool_status
from app.services.supabase_service import supabase_service
from app.core.logging import logger

router = APIRouter(prefix="/health", tags=["health"])


@router.get(
    "/",
    summary="Basic health check",
    description="Basic service health check"
)
async def basic_health():
    """Basic health check endpoint."""
    return {"status": "healthy", "service": "shopify-auth"}


@router.get(
    "/detailed",
    summary="Detailed health check",
    description="Detailed health check including database connectivity"
)
async def detailed_health(db: Session = Depends(get_db)):
    """
    Detailed health check including database connectivity.
    
    Args:
        db: Database session
        
    Returns:
        Detailed health status
    """
    health_status = {
        "service": "shopify-auth",
        "status": "healthy",
        "checks": {
            "database": {"status": "unknown"},
            "supabase": {"status": "unknown"},
            "connection_pool": {"status": "unknown"}
        }
    }
    
    try:
        # Test database connection
        if test_database_connection():
            health_status["checks"]["database"]["status"] = "healthy"
        else:
            health_status["checks"]["database"]["status"] = "unhealthy"
            health_status["status"] = "unhealthy"
        
        # Test Supabase connection
        if await supabase_service.check_connection():
            health_status["checks"]["supabase"]["status"] = "healthy"
        else:
            health_status["checks"]["supabase"]["status"] = "unhealthy"
            health_status["status"] = "unhealthy"
        
        # Get connection pool status
        pool_status = get_connection_pool_status()
        health_status["checks"]["connection_pool"] = {
            "status": "healthy",
            "details": pool_status
        }
        
    except Exception as e:
        logger.error(f"Health check error: {str(e)}")
        health_status["status"] = "unhealthy"
        health_status["error"] = str(e)
    
    return health_status


@router.get(
    "/database",
    summary="Database health check",
    description="Check database connectivity and performance"
)
async def database_health():
    """Database-specific health check."""
    try:
        connection_healthy = test_database_connection()
        pool_status = get_connection_pool_status()
        
        return {
            "database": {
                "connection": "healthy" if connection_healthy else "unhealthy",
                "pool_status": pool_status
            }
        }
    except Exception as e:
        logger.error(f"Database health check error: {str(e)}")
        return {
            "database": {
                "connection": "unhealthy",
                "error": str(e)
            }
        }