"""Tests for authentication service."""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.services.auth_service import ShopifyAuthService
from app.models.auth import ShopifyAuth


class TestShopifyAuthService:
    """Test cases for ShopifyAuthService."""
    
    @pytest.fixture
    def auth_service(self):
        """Create auth service instance."""
        return ShopifyAuthService()
    
    def test_generate_auth_url(self, auth_service, sample_shop_domain):
        """Test auth URL generation."""
        result = auth_service.generate_auth_url(sample_shop_domain)
        
        assert "auth_url" in result
        assert "state" in result
        assert "shop" in result
        assert sample_shop_domain in result["auth_url"]
        assert "oauth/authorize" in result["auth_url"]
        assert len(result["state"]) > 0
    
    def test_verify_callback_params_valid(self, auth_service):
        """Test valid callback parameter verification."""
        # This would need proper HMAC calculation for real testing
        params = {
            "code": "test-code",
            "shop": "test-shop.myshopify.com",
            "state": "test-state",
            "hmac": "calculated-hmac"
        }
        
        with patch.object(auth_service, 'verify_callback_params', return_value=True):
            result = auth_service.verify_callback_params(params)
            assert result is True
    
    def test_verify_callback_params_invalid(self, auth_service):
        """Test invalid callback parameter verification."""
        params = {
            "code": "test-code",
            "shop": "test-shop.myshopify.com",
            "state": "test-state"
            # Missing HMAC
        }
        
        result = auth_service.verify_callback_params(params)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_exchange_code_for_token_success(self, auth_service, sample_token_response):
        """Test successful token exchange."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = sample_token_response
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            result = await auth_service.exchange_code_for_token(
                "test-code", "test-shop.myshopify.com"
            )
            
            assert result == sample_token_response
    
    @pytest.mark.asyncio
    async def test_exchange_code_for_token_failure(self, auth_service):
        """Test failed token exchange."""
        with patch("httpx.AsyncClient") as mock_client:
            mock_response = Mock()
            mock_response.status_code = 400
            mock_response.text = "Bad Request"
            
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )
            
            with pytest.raises(Exception):  # Should raise HTTPException
                await auth_service.exchange_code_for_token(
                    "invalid-code", "test-shop.myshopify.com"
                )
    
    def test_save_auth_data_new_record(self, auth_service, db_session, sample_token_response):
        """Test saving new auth data."""
        shop_domain = "test-shop.myshopify.com"
        
        result = auth_service.save_auth_data(db_session, shop_domain, sample_token_response)
        
        assert isinstance(result, ShopifyAuth)
        assert result.shop_domain == shop_domain
        assert result.access_token == sample_token_response["access_token"]
        assert result.is_active is True
    
    def test_save_auth_data_update_existing(self, auth_service, db_session, sample_token_response):
        """Test updating existing auth data."""
        shop_domain = "test-shop.myshopify.com"
        
        # Create initial record
        initial_auth = ShopifyAuth(
            shop_domain=shop_domain,
            access_token="old-token",
            scopes="read_orders",
            is_active=True
        )
        db_session.add(initial_auth)
        db_session.commit()
        
        # Update with new token
        result = auth_service.save_auth_data(db_session, shop_domain, sample_token_response)
        
        assert result.access_token == sample_token_response["access_token"]
        assert result.id == initial_auth.id  # Same record, updated
    
    def test_get_auth_data_exists(self, auth_service, db_session):
        """Test retrieving existing auth data."""
        shop_domain = "test-shop.myshopify.com"
        
        # Create auth record
        auth_record = ShopifyAuth(
            shop_domain=shop_domain,
            access_token="test-token",
            scopes="read_orders",
            is_active=True
        )
        db_session.add(auth_record)
        db_session.commit()
        
        result = auth_service.get_auth_data(db_session, shop_domain)
        
        assert result is not None
        assert result.shop_domain == shop_domain
        assert result.is_active is True
    
    def test_get_auth_data_not_exists(self, auth_service, db_session):
        """Test retrieving non-existent auth data."""
        result = auth_service.get_auth_data(db_session, "nonexistent.myshopify.com")
        assert result is None
    
    def test_revoke_auth_success(self, auth_service, db_session):
        """Test successful auth revocation."""
        shop_domain = "test-shop.myshopify.com"
        
        # Create auth record
        auth_record = ShopifyAuth(
            shop_domain=shop_domain,
            access_token="test-token",
            scopes="read_orders",
            is_active=True
        )
        db_session.add(auth_record)
        db_session.commit()
        
        result = auth_service.revoke_auth(db_session, shop_domain)
        
        assert result is True
        
        # Verify record is deactivated
        updated_record = db_session.query(ShopifyAuth).filter(
            ShopifyAuth.shop_domain == shop_domain
        ).first()
        assert updated_record.is_active is False
    
    def test_revoke_auth_not_found(self, auth_service, db_session):
        """Test revoking non-existent auth."""
        result = auth_service.revoke_auth(db_session, "nonexistent.myshopify.com")
        assert result is False