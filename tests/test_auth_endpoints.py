"""Tests for authentication API endpoints."""
import pytest
from unittest.mock import patch, Mock
from fastapi.testclient import TestClient
from app.models.auth import ShopifyAuth


class TestAuthEndpoints:
    """Test cases for authentication endpoints."""
    
    def test_initiate_auth_success(self, client, sample_auth_request):
        """Test successful auth initiation."""
        response = client.post("/api/v1/auth/authorize", json=sample_auth_request)
        
        assert response.status_code == 200
        data = response.json()
        assert "auth_url" in data
        assert "state" in data
        assert "shop" in data
    
    def test_initiate_auth_invalid_shop(self, client):
        """Test auth initiation with invalid shop."""
        invalid_request = {"shop": ""}
        response = client.post("/api/v1/auth/authorize", json=invalid_request)
        
        assert response.status_code == 422  # Validation error
    
    @patch('app.services.auth_service.shopify_auth_service.verify_callback_params')
    @patch('app.services.auth_service.shopify_auth_service.exchange_code_for_token')
    @patch('app.services.auth_service.shopify_auth_service.save_auth_data')
    def test_auth_callback_success(
        self, 
        mock_save_auth, 
        mock_exchange_token, 
        mock_verify_params,
        client,
        sample_callback_params,
        sample_token_response,
        db_session
    ):
        """Test successful auth callback."""
        # Mock the service methods
        mock_verify_params.return_value = True
        mock_exchange_token.return_value = sample_token_response
        
        mock_auth_record = Mock(spec=ShopifyAuth)
        mock_auth_record.scopes = "read_orders,write_products"
        mock_save_auth.return_value = mock_auth_record
        
        # Make callback request
        response = client.get(
            "/api/v1/auth/callback",
            params=sample_callback_params
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Authentication successful"
        assert "shop" in data
        assert "scopes" in data
    
    def test_auth_callback_invalid_params(self, client):
        """Test callback with invalid parameters."""
        invalid_params = {
            "code": "test-code",
            "shop": "test-shop.myshopify.com"
            # Missing other required params
        }
        
        response = client.get("/api/v1/auth/callback", params=invalid_params)
        assert response.status_code == 400
    
    def test_check_auth_status_authenticated(self, client, db_session):
        """Test auth status check for authenticated shop."""
        shop_domain = "test-shop.myshopify.com"
        
        # Create auth record
        auth_record = ShopifyAuth(
            shop_domain=shop_domain,
            access_token="test-token",
            scopes="read_orders,write_products",
            is_active=True
        )
        db_session.add(auth_record)
        db_session.commit()
        
        response = client.get(f"/api/v1/auth/status/{shop_domain}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_authenticated"] is True
        assert data["shop_domain"] == shop_domain
        assert "scopes" in data
    
    def test_check_auth_status_not_authenticated(self, client):
        """Test auth status check for non-authenticated shop."""
        shop_domain = "nonexistent.myshopify.com"
        
        response = client.get(f"/api/v1/auth/status/{shop_domain}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["is_authenticated"] is False
    
    def test_revoke_auth_success(self, client, db_session):
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
        
        response = client.delete(f"/api/v1/auth/revoke/{shop_domain}")
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "revoked successfully" in data["message"]
    
    def test_revoke_auth_not_found(self, client):
        """Test revoking non-existent auth."""
        shop_domain = "nonexistent.myshopify.com"
        
        response = client.delete(f"/api/v1/auth/revoke/{shop_domain}")
        assert response.status_code == 404
    
    def test_health_check(self, client):
        """Test health check endpoint."""
        response = client.get("/api/v1/auth/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"