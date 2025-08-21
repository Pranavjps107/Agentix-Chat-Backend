"""
Authentication API routes for Shopify OAuth integration.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.auth import (
    ShopifyAuthRequest,
    ShopifyAuthCallback,
    AuthTokenResponse,
    AuthStatusResponse,
    ErrorResponse
)
from app.services.auth_service import shopify_auth_service
from app.core.logging import logger
from app.core.config import settings  # ✅ make sure you have settings imported

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post(
    "/authorize",
    response_model=Dict[str, str],
    summary="Initiate Shopify OAuth flow",
    description="Generate authorization URL for Shopify OAuth flow"
)
async def initiate_auth(
    auth_request: ShopifyAuthRequest
) -> Dict[str, str]:
    try:
        auth_data = shopify_auth_service.generate_auth_url(auth_request.shop)
        logger.info(f"Initiated auth flow for shop: {auth_request.shop}")
        return auth_data
    except Exception as e:
        logger.error(f"Auth initiation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate authorization flow"
        )


@router.get(
    "/callback",
    summary="Handle OAuth callback",
    description="Handle the OAuth callback from Shopify"
)
async def auth_callback(
    code: str = Query(..., description="Authorization code from Shopify"),
    shop: str = Query(..., description="Shop domain"),
    state: str = Query(None, description="State parameter"),
    hmac: str = Query(None, description="HMAC signature"),
    timestamp: str = Query(None, description="Request timestamp"),
    db: Session = Depends(get_db)
):
    try:
        callback_params = {
            "code": code,
            "shop": shop,
            "state": state,
            "timestamp": timestamp
        }

        if not shopify_auth_service.verify_callback_params(callback_params.copy()):
            logger.warning(f"Invalid callback parameters for shop: {shop}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid callback parameters"
            )

        token_data = await shopify_auth_service.exchange_code_for_token(code, shop)
        auth_record = shopify_auth_service.save_auth_data(db, shop, token_data)

        logger.info(f"Successfully completed OAuth flow for shop: {shop}")

        return {
            "message": "Authentication successful",
            "shop": shop,
            "scopes": auth_record.scopes.split(",")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Callback error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to complete authentication"
        )


@router.get(
    "/status/{shop_domain}",
    response_model=AuthStatusResponse,
    summary="Check authentication status",
    description="Check if a shop is authenticated and get scope information"
)
async def check_auth_status(
    shop_domain: str,
    db: Session = Depends(get_db)
) -> AuthStatusResponse:
    try:
        auth_data = shopify_auth_service.get_auth_data(db, shop_domain)

        if auth_data:
            return AuthStatusResponse(
                is_authenticated=True,
                shop_domain=auth_data.shop_domain,
                scopes=auth_data.scopes.split(","),
                last_updated=auth_data.updated_at or auth_data.created_at
            )
        else:
            return AuthStatusResponse(is_authenticated=False)
    except Exception as e:
        logger.error(f"Status check error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to check authentication status"
        )


@router.delete(
    "/revoke/{shop_domain}",
    summary="Revoke authentication",
    description="Revoke authentication for a shop"
)
async def revoke_auth(
    shop_domain: str,
    db: Session = Depends(get_db)
) -> Dict[str, str]:
    try:
        success = shopify_auth_service.revoke_auth(db, shop_domain)

        if success:
            logger.info(f"Revoked authentication for shop: {shop_domain}")
            return {"message": "Authentication revoked successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active authentication found for this shop"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Revocation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke authentication"
        )


@router.get(
    "/health",
    summary="Health check",
    description="Simple health check endpoint"
)
async def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "shopify-auth"}


# ✅ NEW DEBUG ENDPOINT
@router.get(
    "/debug-config",
    summary="Debug configuration",
    description="Show current configuration for debugging (development only)"
)
async def debug_config():
    """Debug configuration endpoint - REMOVE IN PRODUCTION."""
    if settings.ENVIRONMENT == "production" and not settings.ALLOW_DEBUG_CONFIG:
        raise HTTPException(status_code=404, detail="Not found")


    return {
        "client_id": settings.SHOPIFY_CLIENT_ID,
        "redirect_uri": settings.SHOPIFY_REDIRECT_URI,
        "scopes": settings.SHOPIFY_SCOPES,
        "environment": settings.ENVIRONMENT,
    }
