# app/main.py (Complete Updated Version with All Endpoints)
"""
Complete Shopify integration with comprehensive features and OAuth implementation.
"""
from fastapi import FastAPI, HTTPException, Request, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from contextlib import asynccontextmanager
from typing import List, Optional, Dict, Any
import asyncio
import os
import secrets
import httpx
from urllib.parse import urlencode
from dotenv import load_dotenv
from datetime import datetime, timedelta
import logging
from decimal import Decimal
import json

# Load environment variables
load_dotenv()

# Shopify OAuth Configuration
SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET")
SHOPIFY_REDIRECT_URI = os.getenv("SHOPIFY_REDIRECT_URI", "http://localhost:8000/api/v1/auth/callback")
SHOPIFY_SCOPES = os.getenv("SHOPIFY_SCOPES", "read_orders,write_products,read_customers").split(",")

# In-memory storage (use database in production)
auth_states = {}
access_tokens = {}

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    logger.info("🚀 Starting Agentix Chat Bot - Shopify Integration")
    
    # Validate Shopify credentials
    if not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
        logger.warning("⚠️ Shopify credentials not configured. OAuth will not work.")
    else:
        logger.info("✅ Shopify OAuth credentials configured")
    
    yield
    
    # Shutdown
    logger.info("🛑 Shutting down Agentix Chat Bot")

# Initialize FastAPI app
app = FastAPI(
    title="Agentix Chat Bot - Shopify Integration",
    description="Complete agentic chatbot for Shopify stores with comprehensive data management",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== UTILITY FUNCTIONS ====================

async def make_shopify_request(shop_domain: str, endpoint: str, method: str = "GET", data: dict = None):
    """Make authenticated request to Shopify API."""
    if shop_domain not in access_tokens:
        raise HTTPException(
            status_code=404, 
            detail=f"Shop {shop_domain} not found or not installed. Use /api/v1/auth/authorize to install."
        )
    
    access_token = access_tokens[shop_domain]["access_token"]
    url = f"https://{shop_domain}/admin/api/2023-10/{endpoint}"
    
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            if method.upper() == "GET":
                response = await client.get(url, headers=headers, timeout=30.0)
            elif method.upper() == "POST":
                response = await client.post(url, headers=headers, json=data, timeout=30.0)
            elif method.upper() == "PUT":
                response = await client.put(url, headers=headers, json=data, timeout=30.0)
            elif method.upper() == "DELETE":
                response = await client.delete(url, headers=headers, timeout=30.0)
            else:
                raise HTTPException(status_code=400, detail=f"Unsupported method: {method}")
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Shopify API error: {response.text}"
                )
    
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Request timeout")
    except Exception as e:
        logger.error(f"Error making Shopify request to {shop_domain}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"API request failed: {str(e)}")

async def exchange_code_for_token(code: str, shop_domain: str) -> dict:
    """Exchange authorization code for access token."""
    token_url = f"https://{shop_domain}/admin/oauth/access_token"
    
    payload = {
        "client_id": SHOPIFY_CLIENT_ID,
        "client_secret": SHOPIFY_CLIENT_SECRET,
        "code": code
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            token_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30.0
        )
        
        if response.status_code != 200:
            raise Exception(f"Token exchange failed: {response.status_code} - {response.text}")
        
        return response.json()

async def test_api_call(shop_domain: str, access_token: str) -> dict:
    """Test API call to verify token works."""
    api_url = f"https://{shop_domain}/admin/api/2023-10/shop.json"
    
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(api_url, headers=headers, timeout=30.0)
            
            if response.status_code == 200:
                return response.json().get("shop", {})
            else:
                return {"error": f"API test failed: {response.status_code} - {response.text}"}
    except Exception as e:
        return {"error": f"API test exception: {str(e)}"}

# ==================== CORE ENDPOINTS ====================

@app.get("/")
async def root():
    """Root endpoint with comprehensive status."""
    return {
        "app_name": "Agentix Chat Bot",
        "version": "2.0.0",
        "status": "operational",
        "oauth_ready": bool(SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET),
        "installed_shops": list(access_tokens.keys()),
        "features": {
            "shopify_oauth": True,
            "products_api": True,
            "orders_api": True,
            "customers_api": True,
            "analytics": True,
            "search": True
        },
        "endpoints": {
            "authentication": "/api/v1/auth",
            "health_check": "/api/v1/health",
            "shopify_products": "/api/v1/shopify/shops/{shop_domain}/products",
            "shopify_orders": "/api/v1/shopify/shops/{shop_domain}/orders",
            "shopify_customers": "/api/v1/shopify/shops/{shop_domain}/customers",
            "analytics": "/api/v1/shopify/shops/{shop_domain}/analytics",
            "search": "/api/v1/shopify/shops/{shop_domain}/search",
            "documentation": "/docs"
        }
    }

# ==================== SHOPIFY OAUTH ENDPOINTS ====================

@app.post("/api/v1/auth/authorize")
async def initiate_auth(request: dict):
    """Initiate Shopify OAuth flow."""
    if not SHOPIFY_CLIENT_ID or not SHOPIFY_CLIENT_SECRET:
        raise HTTPException(
            status_code=503, 
            detail="Shopify OAuth not configured. Please set SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET."
        )
    
    shop = request.get("shop", "")
    
    if not shop:
        raise HTTPException(status_code=400, detail="Shop domain required")
    
    # Normalize shop domain
    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com"
    
    # Generate secure state
    state = secrets.token_urlsafe(32)
    auth_states[state] = {
        "shop": shop, 
        "timestamp": datetime.now().isoformat(),
        "initiated_by": "api"
    }
    
    # Build authorization URL
    params = {
        "client_id": SHOPIFY_CLIENT_ID,
        "scope": ",".join(SHOPIFY_SCOPES),
        "redirect_uri": SHOPIFY_REDIRECT_URI,
        "state": state,
        "response_type": "code"
    }
    
    auth_url = f"https://{shop}/admin/oauth/authorize?{urlencode(params)}"
    
    return {
        "auth_url": auth_url,
        "state": state,
        "shop": shop,
        "message": "Click auth_url to install Agentix Chat Bot",
        "scopes": SHOPIFY_SCOPES,
        "redirect_uri": SHOPIFY_REDIRECT_URI
    }

@app.get("/api/v1/auth/callback")
async def auth_callback(code: str = None, state: str = None, shop: str = None):
    """Handle OAuth callback and exchange code for token."""
    
    if not code or not shop or not state:
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>OAuth Error - Missing Parameters</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                       margin: 0; padding: 40px; background: #f6f6f7; text-align: center; }
                .error { color: #d73a49; }
            </style>
        </head>
        <body>
            <h1 class="error">❌ Missing Parameters</h1>
            <p>Required: code, shop, and state parameters</p>
            <p>This usually indicates an issue with the OAuth flow.</p>
        </body>
        </html>
        """, status_code=400)
    
    # Verify state parameter
    if state not in auth_states or auth_states[state]["shop"] != shop:
        auth_states.pop(state, None)  # Clean up invalid state
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head>
            <title>OAuth Error - Invalid State</title>
            <style>
                body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                       margin: 0; padding: 40px; background: #f6f6f7; text-align: center; }
                .error { color: #d73a49; }
            </style>
        </head>
        <body>
            <h1 class="error">❌ Invalid State</h1>
            <p>State verification failed. This may be a security issue.</p>
            <p>Please try the installation process again.</p>
        </body>
        </html>
        """, status_code=400)
    
    # Clean up used state
    auth_states.pop(state, None)
    
    try:
        # Exchange authorization code for access token
        logger.info(f"Exchanging code for token for shop: {shop}")
        token_data = await exchange_code_for_token(code, shop)
        access_token = token_data.get("access_token")
        
        if not access_token:
            raise Exception("No access token received from Shopify")
        
        # Store access token securely
        access_tokens[shop] = {
            "access_token": access_token,
            "scope": token_data.get("scope", ",".join(SHOPIFY_SCOPES)),
            "installed_at": datetime.now().isoformat(),
            "last_verified": datetime.now().isoformat()
        }
        
        logger.info(f"✅ Successfully stored access token for {shop}")
        
        # Test API call to verify token works
        shop_info = await test_api_call(shop, access_token)
        
        # Success page
        success_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Agentix Chat Bot - Installation Success</title>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                    margin: 0; padding: 20px; background: #f6f6f7; color: #333;
                }}
                .container {{ 
                    max-width: 700px; margin: 0 auto; background: white; 
                    border-radius: 8px; padding: 40px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); 
                }}
                .success {{ color: #28a745; font-size: 28px; margin-bottom: 20px; text-align: center; }}
                .details {{ 
                    background: #f8f9fa; padding: 20px; border-radius: 6px; margin: 20px 0; 
                    border-left: 4px solid #28a745;
                }}
                .shop-info {{ 
                    background: #e3f2fd; padding: 20px; border-radius: 6px; margin: 15px 0; 
                    border-left: 4px solid #2196f3;
                }}
                .api-endpoints {{ margin: 20px 0; }}
                .endpoint {{ 
                    background: #f1f3f4; padding: 8px 12px; border-radius: 4px; 
                    font-family: monospace; margin: 5px 0; font-size: 14px;
                }}
                .btn {{ 
                    display: inline-block; background: #5c6ac4; color: white; 
                    padding: 12px 24px; text-decoration: none; border-radius: 4px; 
                    margin: 10px 5px 0 0; transition: background 0.3s;
                }}
                .btn:hover {{ background: #4c5bd4; }}
                .btn-secondary {{ background: #6c757d; }}
                .btn-secondary:hover {{ background: #545b62; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div style="font-size: 60px; text-align: center; margin: 20px 0;">🎉</div>
                <h1 class="success">Agentix Chat Bot Installed Successfully!</h1>
                
                <div class="details">
                    <h3>Installation Details</h3>
                    <p><strong>Shop:</strong> {shop}</p>
                    <p><strong>Installed:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
                    <p><strong>Scopes Granted:</strong> {', '.join(SHOPIFY_SCOPES)}</p>
                    <p><strong>Status:</strong> Active and Ready</p>
                </div>
                
                <div class="shop-info">
                    <h3>📊 Shop Information Retrieved</h3>
                    <p><strong>Shop Name:</strong> {shop_info.get('name', 'N/A')}</p>
                    <p><strong>Email:</strong> {shop_info.get('email', 'N/A')}</p>
                    <p><strong>Domain:</strong> {shop_info.get('domain', 'N/A')}</p>
                    <p><strong>Currency:</strong> {shop_info.get('currency', 'N/A')}</p>
                    <p><strong>Plan:</strong> {shop_info.get('plan_name', 'N/A')}</p>
                </div>
                
                <div class="api-endpoints">
                    <h3>🔗 Available API Endpoints</h3>
                    <div class="endpoint">GET /api/v1/shopify/shops/{shop}/products - Get products</div>
                    <div class="endpoint">GET /api/v1/shopify/shops/{shop}/orders - Get orders</div>
                    <div class="endpoint">GET /api/v1/shopify/shops/{shop}/customers - Get customers</div>
                    <div class="endpoint">GET /api/v1/shopify/shops/{shop}/analytics/summary - Get analytics</div>
                    <div class="endpoint">GET /api/v1/shopify/shops/{shop}/search - Search all data</div>
                    <div class="endpoint">GET /docs - API Documentation</div>
                </div>
                
                <p style="text-align: center; margin: 30px 0;">
                    <strong>🚀 Your Agentix Chat Bot is now connected and ready to use!</strong>
                </p>
                
                <div style="text-align: center;">
                    <a href="https://{shop}/admin/apps" class="btn">Go to Shopify Apps</a>
                    <a href="/api/v1/shopify/shops/{shop}/products" class="btn btn-secondary">Test Products API</a>
                    <a href="/docs" class="btn btn-secondary">View API Docs</a>
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=success_html)
        
    except Exception as e:
        logger.error(f"OAuth callback failed for {shop}: {str(e)}")
        
        error_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Agentix Chat Bot - Installation Failed</title>
            <style>
                body {{ 
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                    margin: 0; padding: 40px; background: #f6f6f7; text-align: center; 
                }}
                .error {{ color: #dc3545; margin: 20px 0; }}
                .details {{ background: #f8d7da; padding: 20px; border-radius: 6px; margin: 20px 0; 
                           border-left: 4px solid #dc3545; text-align: left; }}
            </style>
        </head>
        <body>
            <h1 class="error">❌ Installation Failed</h1>
            <div class="details">
                <p><strong>Error:</strong> {str(e)}</p>
                <p><strong>Shop:</strong> {shop}</p>
                <p><strong>Time:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}</p>
            </div>
            <p>Please try the installation process again, or contact support if the issue persists.</p>
        </body>
        </html>
        """
        return HTMLResponse(content=error_html, status_code=500)

# ==================== SHOP MANAGEMENT ENDPOINTS ====================

@app.get("/api/v1/shops")
async def list_installed_shops():
    """List all shops with installed tokens."""
    shops_data = []
    
    for shop, data in access_tokens.items():
        # Test token validity
        test_result = await test_api_call(shop, data["access_token"])
        token_valid = not test_result.get("error")
        
        shops_data.append({
            "shop": shop,
            "installed_at": data["installed_at"],
            "scope": data["scope"],
            "token_valid": token_valid,
            "last_verified": data.get("last_verified"),
            "shop_name": test_result.get("name") if token_valid else None
        })
    
    return {
        "installed_shops": shops_data,
        "total_installations": len(access_tokens),
        "active_installations": sum(1 for shop in shops_data if shop["token_valid"])
    }

@app.get("/api/v1/shops/{shop_domain}/info")
async def get_shop_info(shop_domain: str):
    """Get shop information using stored access token."""
    shop_info = await make_shopify_request(shop_domain, "shop.json")
    
    # Update last verified timestamp
    access_tokens[shop_domain]["last_verified"] = datetime.now().isoformat()
    
    return {
        "shop": shop_domain,
        "info": shop_info.get("shop", {}),
        "token_status": "valid",
        "installation_data": access_tokens[shop_domain]
    }

@app.delete("/api/v1/shops/{shop_domain}")
async def uninstall_shop(shop_domain: str):
    """Remove shop installation (uninstall)."""
    if shop_domain not in access_tokens:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    # Remove stored token
    removed_data = access_tokens.pop(shop_domain)
    
    logger.info(f"Uninstalled shop: {shop_domain}")
    
    return {
        "message": f"Shop {shop_domain} has been uninstalled successfully",
        "removed_at": datetime.now().isoformat(),
        "was_installed_at": removed_data.get("installed_at")
    }

# ==================== PRODUCTS ENDPOINTS ====================

@app.get("/api/v1/shopify/shops/{shop_domain}/products")
async def get_products(
    shop_domain: str,
    limit: int = Query(50, ge=1, le=250, description="Number of products to return"),
    page_info: Optional[str] = Query(None, description="Page info for pagination"),
    status: Optional[str] = Query(None, description="Filter by status (active, archived, draft)"),
    vendor: Optional[str] = Query(None, description="Filter by vendor"),
    product_type: Optional[str] = Query(None, description="Filter by product type"),
    created_at_min: Optional[str] = Query(None, description="Filter by creation date (ISO format)"),
    updated_at_min: Optional[str] = Query(None, description="Filter by update date (ISO format)")
):
    """Get products from Shopify with filtering options."""
    
    # Build query parameters
    params = {"limit": limit}
    
    if page_info:
        params["page_info"] = page_info
    if status:
        params["status"] = status
    if vendor:
        params["vendor"] = vendor
    if product_type:
        params["product_type"] = product_type
    if created_at_min:
        params["created_at_min"] = created_at_min
    if updated_at_min:
        params["updated_at_min"] = updated_at_min
    
    # Build endpoint with parameters
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    endpoint = f"products.json?{query_string}"
    
    data = await make_shopify_request(shop_domain, endpoint)
    
    return {
        "shop": shop_domain,
        "products": data.get("products", []),
        "count": len(data.get("products", [])),
        "parameters": params
    }

@app.get("/api/v1/shopify/shops/{shop_domain}/products/{product_id}")
async def get_product(shop_domain: str, product_id: int):
    """Get a single product by ID."""
    
    endpoint = f"products/{product_id}.json"
    data = await make_shopify_request(shop_domain, endpoint)
    
    return {
        "shop": shop_domain,
        "product": data.get("product", {}),
        "product_id": product_id
    }

# ==================== ORDERS ENDPOINTS ====================

@app.get("/api/v1/shopify/shops/{shop_domain}/orders")
async def get_orders(
    shop_domain: str,
    limit: int = Query(50, ge=1, le=250, description="Number of orders to return"),
    status: Optional[str] = Query("any", description="Order status filter"),
    financial_status: Optional[str] = Query(None, description="Financial status filter"),
    fulfillment_status: Optional[str] = Query(None, description="Fulfillment status filter"),
    created_at_min: Optional[str] = Query(None, description="Filter by creation date (ISO format)"),
    created_at_max: Optional[str] = Query(None, description="Filter by creation date (ISO format)"),
    updated_at_min: Optional[str] = Query(None, description="Filter by update date (ISO format)")
):
    """Get orders from Shopify with filtering options."""
    
    # Build query parameters
    params = {"limit": limit, "status": status}
    
    if financial_status:
        params["financial_status"] = financial_status
    if fulfillment_status:
        params["fulfillment_status"] = fulfillment_status
    if created_at_min:
        params["created_at_min"] = created_at_min
    if created_at_max:
        params["created_at_max"] = created_at_max
    if updated_at_min:
        params["updated_at_min"] = updated_at_min
    
    # Build endpoint with parameters
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    endpoint = f"orders.json?{query_string}"
    
    data = await make_shopify_request(shop_domain, endpoint)
    
    return {
        "shop": shop_domain,
        "orders": data.get("orders", []),
        "count": len(data.get("orders", [])),
        "parameters": params
    }

@app.get("/api/v1/shopify/shops/{shop_domain}/orders/{order_id}")
async def get_order(shop_domain: str, order_id: int):
    """Get a single order by ID."""
    
    endpoint = f"orders/{order_id}.json"
    data = await make_shopify_request(shop_domain, endpoint)
    
    return {
        "shop": shop_domain,
        "order": data.get("order", {}),
        "order_id": order_id
    }

# ==================== CUSTOMERS ENDPOINTS ====================

@app.get("/api/v1/shopify/shops/{shop_domain}/customers")
async def get_customers(
    shop_domain: str,
    limit: int = Query(50, ge=1, le=250, description="Number of customers to return"),
    created_at_min: Optional[str] = Query(None, description="Filter by creation date (ISO format)"),
    updated_at_min: Optional[str] = Query(None, description="Filter by update date (ISO format)")
):
    """Get customers from Shopify."""
    
    # Build query parameters
    params = {"limit": limit}
    
    if created_at_min:
        params["created_at_min"] = created_at_min
    if updated_at_min:
        params["updated_at_min"] = updated_at_min
    
    # Build endpoint with parameters
    query_string = "&".join([f"{k}={v}" for k, v in params.items()])
    endpoint = f"customers.json?{query_string}"
    
    data = await make_shopify_request(shop_domain, endpoint)
    
    return {
        "shop": shop_domain,
        "customers": data.get("customers", []),
        "count": len(data.get("customers", [])),
        "parameters": params
    }

@app.get("/api/v1/shopify/shops/{shop_domain}/customers/{customer_id}")
async def get_customer(shop_domain: str, customer_id: int):
    """Get a single customer by ID."""
    
    endpoint = f"customers/{customer_id}.json"
    data = await make_shopify_request(shop_domain, endpoint)
    
    return {
        "shop": shop_domain,
        "customer": data.get("customer", {}),
        "customer_id": customer_id
    }

# ==================== SEARCH ENDPOINT ====================

@app.get("/api/v1/shopify/shops/{shop_domain}/search")
async def universal_search(
    shop_domain: str,
    query: str = Query(..., description="Search query"),
    search_type: Optional[str] = Query(None, description="Limit search to: products, orders, customers"),
    limit: int = Query(20, ge=1, le=100, description="Maximum results per type")
):
    """Universal search across products, orders, and customers."""
    
    results = {
        "query": query,
        "shop": shop_domain,
        "products": [],
        "orders": [],
        "customers": [],
        "total_results": 0
    }
    
    try:
        # Search products
        if not search_type or search_type == "products":
            try:
                products_data = await make_shopify_request(
                    shop_domain, 
                    f"products.json?limit={limit}&title={query}"
                )
                results["products"] = products_data.get("products", [])
            except Exception as e:
                logger.error(f"Error searching products: {str(e)}")
        
        # Search orders (by order number or customer email)
        if not search_type or search_type == "orders":
            try:
                # Try searching by order name/number
                orders_data = await make_shopify_request(
                    shop_domain, 
                    f"orders.json?limit={limit}&name={query}&status=any"
                )
                results["orders"] = orders_data.get("orders", [])
            except Exception as e:
                logger.error(f"Error searching orders: {str(e)}")
        
        # Search customers
        if not search_type or search_type == "customers":
            try:
                # Note: Shopify doesn't support direct customer search via API
                # This would require getting all customers and filtering locally
                # For now, we'll leave it empty but the structure is there
                results["customers"] = []
            except Exception as e:
                logger.error(f"Error searching customers: {str(e)}")
        
        results["total_results"] = len(results["products"]) + len(results["orders"]) + len(results["customers"])
        
        return results
        
    except Exception as e:
        logger.error(f"Error in universal search for {shop_domain}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Search failed: {str(e)}"
        )

# ==================== ANALYTICS ENDPOINTS ====================

@app.get("/api/v1/shopify/shops/{shop_domain}/analytics/summary")
async def get_analytics_summary(
    shop_domain: str,
    days_back: int = Query(30, ge=1, le=365, description="Number of days to analyze")
):
    """Get analytics summary for the shop."""
    
    try:
        # Calculate date range
        end_date = datetime.utcnow()
        start_date = end_date - timedelta(days=days_back)
        start_date_str = start_date.isoformat()
        
        # Get recent orders for analytics
        orders_data = await make_shopify_request(
            shop_domain, 
            f"orders.json?limit=250&status=any&created_at_min={start_date_str}"
        )
        orders = orders_data.get("orders", [])
        
        # Get all products for product analytics
        products_data = await make_shopify_request(shop_domain, "products.json?limit=250")
        products = products_data.get("products", [])
        
        # Get customers count
        customers_data = await make_shopify_request(shop_domain, "customers/count.json")
        total_customers = customers_data.get("count", 0)
        
        # Calculate metrics
        total_orders = len(orders)
        total_revenue = sum(float(order.get("total_price", 0)) for order in orders)
        avg_order_value = total_revenue / total_orders if total_orders > 0 else 0
        
        # Order status breakdown
        paid_orders = [o for o in orders if o.get("financial_status") in ["paid", "partially_paid"]]
        pending_orders = [o for o in orders if o.get("financial_status") in ["pending", "authorized"]]
        cancelled_orders = [o for o in orders if o.get("financial_status") == "cancelled"]
        
        # Product metrics
        active_products = [p for p in products if p.get("status") == "active"]
        draft_products = [p for p in products if p.get("status") == "draft"]
        archived_products = [p for p in products if p.get("status") == "archived"]
        
        # Top products by quantity sold
        product_sales = {}
        for order in orders:
            for item in order.get("line_items", []):
                product_title = item.get("title", "Unknown Product")
                quantity = int(item.get("quantity", 0))
                product_sales[product_title] = product_sales.get(product_title, 0) + quantity
        
        top_products = sorted(product_sales.items(), key=lambda x: x[1], reverse=True)[:10]
        
        return {
            "summary": {
                "period_days": days_back,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "total_orders": total_orders,
                "total_revenue": round(total_revenue, 2),
                "average_order_value": round(avg_order_value, 2),
                "total_products": len(products),
                "active_products": len(active_products),
                "total_customers": total_customers
            },
            "order_breakdown": {
                "paid": len(paid_orders),
                "pending": len(pending_orders),
                "cancelled": len(cancelled_orders)
            },
            "product_breakdown": {
                "active": len(active_products),
                "draft": len(draft_products),
                "archived": len(archived_products)
            },
            "top_products": [
                {
                    "product": product,
                    "quantity_sold": quantity
                } for product, quantity in top_products
            ]
        }
        
    except Exception as e:
        logger.error(f"Error getting analytics for {shop_domain}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get analytics: {str(e)}"
        )

# ==================== INVENTORY ENDPOINTS ====================

@app.get("/api/v1/shopify/shops/{shop_domain}/inventory")
async def get_inventory_summary(
    shop_domain: str,
    low_stock_threshold: int = Query(10, description="Threshold for low stock warning")
):
    """Get inventory summary with low stock alerts."""
    
    try:
        # Get all products with variants
        products_data = await make_shopify_request(shop_domain, "products.json?limit=250")
        products = products_data.get("products", [])
        
        inventory_summary = {
            "total_products": len(products),
            "total_variants": 0,
            "low_stock_products": [],
            "out_of_stock_products": [],
            "total_inventory_value": 0,
            "low_stock_threshold": low_stock_threshold
        }
        
        for product in products:
            for variant in product.get("variants", []):
                inventory_summary["total_variants"] += 1
                
                inventory_quantity = variant.get("inventory_quantity", 0)
                price = float(variant.get("price", 0))
                inventory_summary["total_inventory_value"] += inventory_quantity * price
                
                if inventory_quantity == 0:
                    inventory_summary["out_of_stock_products"].append({
                        "product_title": product.get("title"),
                        "variant_title": variant.get("title"),
                        "sku": variant.get("sku"),
                        "price": price,
                        "inventory_quantity": inventory_quantity
                    })
                elif inventory_quantity <= low_stock_threshold:
                    inventory_summary["low_stock_products"].append({
                        "product_title": product.get("title"),
                        "variant_title": variant.get("title"),
                        "sku": variant.get("sku"),
                        "price": price,
                        "inventory_quantity": inventory_quantity
                    })
        
        inventory_summary["total_inventory_value"] = round(inventory_summary["total_inventory_value"], 2)
        
        return inventory_summary
        
    except Exception as e:
        logger.error(f"Error getting inventory for {shop_domain}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get inventory: {str(e)}"
        )

# ==================== WEBHOOKS ENDPOINTS ====================

@app.get("/api/v1/shopify/shops/{shop_domain}/webhooks")
async def get_webhooks(shop_domain: str):
    """Get all configured webhooks for the shop."""
    
    data = await make_shopify_request(shop_domain, "webhooks.json")
    
    return {
        "shop": shop_domain,
        "webhooks": data.get("webhooks", []),
        "count": len(data.get("webhooks", []))
    }

@app.post("/api/v1/shopify/shops/{shop_domain}/webhooks")
async def create_webhook(
    shop_domain: str,
    webhook_data: dict
):
    """Create a new webhook for the shop."""
    
    data = await make_shopify_request(
        shop_domain, 
        "webhooks.json", 
        method="POST",
        data={"webhook": webhook_data}
    )
    
    return {
        "shop": shop_domain,
        "webhook": data.get("webhook", {}),
        "message": "Webhook created successfully"
    }

# ==================== COLLECTIONS ENDPOINTS ====================

@app.get("/api/v1/shopify/shops/{shop_domain}/collections")
async def get_collections(
    shop_domain: str,
    limit: int = Query(50, ge=1, le=250, description="Number of collections to return")
):
    """Get collections from Shopify."""
    
    # Get both custom collections and smart collections
    custom_collections_data = await make_shopify_request(
        shop_domain, f"custom_collections.json?limit={limit}"
    )
    smart_collections_data = await make_shopify_request(
        shop_domain, f"smart_collections.json?limit={limit}"
    )
    
    return {
        "shop": shop_domain,
        "custom_collections": custom_collections_data.get("custom_collections", []),
        "smart_collections": smart_collections_data.get("smart_collections", []),
        "total_custom": len(custom_collections_data.get("custom_collections", [])),
        "total_smart": len(smart_collections_data.get("smart_collections", []))
    }

@app.get("/api/v1/shopify/shops/{shop_domain}/collections/{collection_id}/products")
async def get_collection_products(
    shop_domain: str,
    collection_id: int,
    limit: int = Query(50, ge=1, le=250, description="Number of products to return")
):
    """Get products in a specific collection."""
    
    endpoint = f"collections/{collection_id}/products.json?limit={limit}"
    data = await make_shopify_request(shop_domain, endpoint)
    
    return {
        "shop": shop_domain,
        "collection_id": collection_id,
        "products": data.get("products", []),
        "count": len(data.get("products", []))
    }

# ==================== HEALTH CHECK ====================

@app.get("/api/v1/health")
async def health_check():
    """Comprehensive health check."""
    health_data = {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "version": "2.0.0",
        "checks": {}
    }
    
    # Check Shopify credentials
    health_data["checks"]["shopify_oauth"] = {
        "status": "configured" if (SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET) else "not_configured",
        "client_id_present": bool(SHOPIFY_CLIENT_ID),
        "client_secret_present": bool(SHOPIFY_CLIENT_SECRET)
    }
    
    # Check installed shops
    health_data["checks"]["installations"] = {
        "total_shops": len(access_tokens),
        "shops": list(access_tokens.keys())
    }
    
    # Test API connectivity for installed shops
    api_tests = {}
    for shop_domain in list(access_tokens.keys())[:3]:  # Test up to 3 shops
        try:
            test_result = await test_api_call(shop_domain, access_tokens[shop_domain]["access_token"])
            api_tests[shop_domain] = "healthy" if not test_result.get("error") else "error"
        except Exception:
            api_tests[shop_domain] = "error"
    
    health_data["checks"]["api_connectivity"] = api_tests
    
    # Overall status
    if not (SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET):
        health_data["status"] = "degraded"
    
    return health_data

# ==================== ERROR HANDLERS ====================

@app.exception_handler(404)
async def not_found_handler(request: Request, exc: HTTPException):
    """Custom 404 handler."""
    return JSONResponse(
        status_code=404,
        content={
            "error": "Not Found",
            "message": "The requested endpoint was not found",
            "available_endpoints": {
                "root": "/",
                "health": "/api/v1/health",
                "auth": "/api/v1/auth/authorize",
                "shops": "/api/v1/shops",
                "products": "/api/v1/shopify/shops/{shop_domain}/products",
                "orders": "/api/v1/shopify/shops/{shop_domain}/orders",
                "customers": "/api/v1/shopify/shops/{shop_domain}/customers",
                "analytics": "/api/v1/shopify/shops/{shop_domain}/analytics/summary",
                "search": "/api/v1/shopify/shops/{shop_domain}/search",
                "docs": "/docs"
            }
        }
    )

@app.exception_handler(500)
async def internal_error_handler(request: Request, exc: Exception):
    """Custom 500 handler."""
    logger.error(f"Internal server error: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected error occurred",
            "timestamp": datetime.now().isoformat()
        }
    )

# ==================== MAIN ====================

if __name__ == "__main__":
    import uvicorn
    
    # Configuration
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", 8000))
    debug = os.getenv("DEBUG", "true").lower() == "true"
    log_level = os.getenv("LOG_LEVEL", "info").lower()
    
    logger.info(f"Starting server on {host}:{port}")
    logger.info(f"Debug mode: {debug}")
    
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=debug,
        log_level=log_level
    )