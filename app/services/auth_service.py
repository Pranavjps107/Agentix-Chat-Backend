"""
Core authentication service for handling Shopify OAuth flow.
"""
import secrets
import hashlib
import hmac
import base64
from typing import Optional, Dict, Any, List
from urllib.parse import urlencode, parse_qs, urlparse
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.core.config import settings
from app.models.auth import ShopifyAuth
from app.core.logging import logger


class ShopifyAuthService:
    """Service class for handling Shopify OAuth authentication."""
    
    def __init__(self):
        # ✅ FIXED: Use actual credentials from settings, not hardcoded values
        self.client_id = settings.SHOPIFY_CLIENT_ID
        self.client_secret = settings.SHOPIFY_CLIENT_SECRET
        self.redirect_uri = settings.SHOPIFY_REDIRECT_URI
        self.scopes = settings.SHOPIFY_SCOPES
        
        # Verify credentials are loaded correctly
        if not self.client_id or self.client_id == "test":
            raise ValueError("❌ SHOPIFY_CLIENT_ID not loaded correctly!")
            
        if not self.client_secret or self.client_secret == "test":
            raise ValueError("❌ SHOPIFY_CLIENT_SECRET not loaded correctly!")
        
        # Log the configuration (without secrets) for debugging
        logger.info(f"Shopify Auth Service initialized:")
        logger.info(f"  Client ID: {self.client_id[:10]}...")
        logger.info(f"  Redirect URI: {self.redirect_uri}")
        logger.info(f"  Scopes: {self.scopes}")
    
    def generate_auth_url(self, shop_domain: str) -> Dict[str, str]:
        """
        Generate Shopify OAuth authorization URL.
        
        Args:
            shop_domain: The shop's myshopify.com domain
            
        Returns:
            Dictionary containing auth_url and state
        """
        # Generate secure state parameter
        state = secrets.token_urlsafe(32)
        
        # Build authorization URL with REAL credentials
        params = {
            "client_id": self.client_id,  # ✅ This is now your REAL client ID
            "scope": ",".join(self.scopes),
            "redirect_uri": self.redirect_uri,
            "state": state,
            "response_type": "code"
        }
        
        auth_url = f"https://{shop_domain}/admin/oauth/authorize?{urlencode(params)}"
        
        logger.info(f"Generated auth URL for shop: {shop_domain}")
        logger.info(f"Using client_id: {self.client_id[:10]}...")  # Only log first 10 chars
        
        return {
            "auth_url": auth_url,
            "state": state,
            "shop": shop_domain
        }
    
    def verify_webhook_signature(self, data: bytes, signature: str) -> bool:
        """
        Verify Shopify webhook signature.
        
        Args:
            data: Raw request body
            signature: HMAC signature from header
            
        Returns:
            True if signature is valid
        """
        calculated_hmac = base64.b64encode(
            hmac.new(
                self.client_secret.encode('utf-8'),
                data,
                digestmod=hashlib.sha256
            ).digest()
        ).decode()
        
        return hmac.compare_digest(calculated_hmac, signature)
    
    def verify_callback_params(self, params: Dict[str, Any]) -> bool:
        """
        Verify OAuth callback parameters.
        
        Args:
            params: Callback parameters from Shopify
            
        Returns:
            True if parameters are valid
        """
        if not params.get("hmac"):
            return False
        
        # Extract HMAC and remove it from params for verification
        received_hmac = params.pop("hmac")
        
        # Create query string from sorted parameters
        query_string = "&".join([f"{k}={v}" for k, v in sorted(params.items())])
        
        # Calculate expected HMAC
        calculated_hmac = hmac.new(
            self.client_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(calculated_hmac, received_hmac)
    
    async def exchange_code_for_token(self, code: str, shop_domain: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.
        
        Args:
            code: Authorization code from callback
            shop_domain: Shop domain
            
        Returns:
            Token response from Shopify
        """
        token_url = f"https://{shop_domain}/admin/oauth/access_token"
        
        payload = {
            "client_id": self.client_id,  # ✅ Real client ID
            "client_secret": self.client_secret,  # ✅ Real client secret
            "code": code
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    token_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    logger.error(f"Token exchange failed: {response.text}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Failed to exchange code for token"
                    )
                
                token_data = response.json()
                logger.info(f"Successfully exchanged token for shop: {shop_domain}")
                
                return token_data
                
            except httpx.TimeoutException:
                logger.error(f"Token exchange timeout for shop: {shop_domain}")
                raise HTTPException(
                    status_code=status.HTTP_408_REQUEST_TIMEOUT,
                    detail="Token exchange request timed out"
                )
            except Exception as e:
                logger.error(f"Token exchange error: {str(e)}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Internal server error during token exchange"
                )
    
    def save_auth_data(self, db: Session, shop_domain: str, token_data: Dict[str, Any]) -> ShopifyAuth:
        """
        Save authentication data to database.
        
        Args:
            db: Database session
            shop_domain: Shop domain
            token_data: Token response from Shopify
            
        Returns:
            Saved ShopifyAuth instance
        """
        # Check if auth record already exists
        existing_auth = db.query(ShopifyAuth).filter(
            ShopifyAuth.shop_domain == shop_domain
        ).first()
        
        if existing_auth:
            # Update existing record
            existing_auth.access_token = token_data["access_token"]
            existing_auth.scopes = token_data.get("scope", ",".join(self.scopes))
            existing_auth.is_active = True
            db.commit()
            db.refresh(existing_auth)
            logger.info(f"Updated auth data for shop: {shop_domain}")
            return existing_auth
        else:
            # Create new record
            auth_record = ShopifyAuth(
                shop_domain=shop_domain,
                access_token=token_data["access_token"],
                scopes=token_data.get("scope", ",".join(self.scopes)),
                is_active=True
            )
            db.add(auth_record)
            db.commit()
            db.refresh(auth_record)
            logger.info(f"Created new auth record for shop: {shop_domain}")
            return auth_record
    
    def get_auth_data(self, db: Session, shop_domain: str) -> Optional[ShopifyAuth]:
        """
        Retrieve authentication data for a shop.
        
        Args:
            db: Database session
            shop_domain: Shop domain
            
        Returns:
            ShopifyAuth instance or None
        """
        return db.query(ShopifyAuth).filter(
            ShopifyAuth.shop_domain == shop_domain,
            ShopifyAuth.is_active == True
        ).first()
    
    def revoke_auth(self, db: Session, shop_domain: str) -> bool:
        """
        Revoke authentication for a shop.
        
        Args:
            db: Database session
            shop_domain: Shop domain
            
        Returns:
            True if revoked successfully
        """
        auth_record = self.get_auth_data(db, shop_domain)
        
        if auth_record:
            auth_record.is_active = False
            db.commit()
            logger.info(f"Revoked auth for shop: {shop_domain}")
            return True
        
        return False


# Global service instance
shopify_auth_service = ShopifyAuthService()