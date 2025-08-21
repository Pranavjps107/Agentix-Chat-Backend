"""
Complete token exchange implementation for your Shopify app
"""
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import os
import secrets
import httpx
from urllib.parse import urlencode
from dotenv import load_dotenv
import json
from datetime import datetime

# Load environment variables
load_dotenv()

app = FastAPI(
    title="Agentix Chat Bot - Shopify Integration",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Shopify credentials
SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET")
SHOPIFY_REDIRECT_URI = os.getenv("SHOPIFY_REDIRECT_URI", "http://localhost:8000/api/v1/auth/callback")
SHOPIFY_SCOPES = os.getenv("SHOPIFY_SCOPES", "read_orders,write_products,read_customers").split(",")

# In-memory storage (use database in production)
auth_states = {}
access_tokens = {}

@app.get("/")
async def root():
    return {
        "app_name": "Agentix Chat Bot",
        "status": "operational",
        "installed_shops": list(access_tokens.keys()),
        "oauth_ready": bool(SHOPIFY_CLIENT_ID and SHOPIFY_CLIENT_SECRET)
    }

@app.post("/api/v1/auth/authorize")
async def initiate_auth(request: dict):
    """Initiate OAuth flow."""
    shop = request.get("shop", "")
    
    if not shop:
        raise HTTPException(status_code=400, detail="Shop domain required")
    
    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com"
    
    state = secrets.token_urlsafe(32)
    auth_states[state] = {"shop": shop, "timestamp": datetime.now().isoformat()}
    
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
        "client_id": SHOPIFY_CLIENT_ID[:10] + "...",
        "scopes": SHOPIFY_SCOPES
    }

@app.get("/api/v1/auth/callback")
async def auth_callback(code: str = None, state: str = None, shop: str = None):
    """Handle OAuth callback and exchange code for token."""
    
    if not code or not shop or not state:
        return HTMLResponse("""
        <html><body>
            <h1>❌ Missing Parameters</h1>
            <p>Required: code, shop, and state parameters</p>
        </body></html>
        """, status_code=400)
    
    # Verify state
    if state not in auth_states or auth_states[state]["shop"] != shop:
        return HTMLResponse("""
        <html><body>
            <h1>❌ Invalid State</h1>
            <p>State verification failed</p>
        </body></html>
        """, status_code=400)
    
    # Remove used state
    auth_states.pop(state, None)
    
    try:
        # Exchange code for access token
        token_data = await exchange_code_for_token(code, shop)
        access_token = token_data.get("access_token")
        
        if not access_token:
            raise Exception("No access token received")
        
        # Store access token (use database in production)
        access_tokens[shop] = {
            "access_token": access_token,
            "scope": token_data.get("scope", ",".join(SHOPIFY_SCOPES)),
            "installed_at": datetime.now().isoformat()
        }
        
        # Test API call to verify token works
        shop_info = await test_api_call(shop, access_token)
        
        # Success page
        success_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Agentix Chat Bot - Installation Success</title>
            <style>
                body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                       margin: 0; padding: 40px; background: #f6f6f7; }}
                .container {{ max-width: 600px; margin: 0 auto; background: white; 
                            border-radius: 8px; padding: 40px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
                .success {{ color: #00a651; font-size: 24px; margin-bottom: 20px; }}
                .details {{ background: #f8f9fa; padding: 20px; border-radius: 6px; margin: 20px 0; }}
                .token {{ font-family: monospace; background: #e3f2fd; padding: 10px; 
                         border-radius: 4px; word-break: break-all; }}
                .btn {{ display: inline-block; background: #5c6ac4; color: white; 
                       padding: 12px 24px; text-decoration: none; border-radius: 4px; 
                       margin: 10px 5px 0 0; }}
                .shop-info {{ margin: 15px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="success">✅ Agentix Chat Bot Installed Successfully!</h1>
                
                <div class="details">
                    <p><strong>Shop:</strong> {shop}</p>
                    <p><strong>Installed:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Scopes:</strong> {', '.join(SHOPIFY_SCOPES)}</p>
                </div>
                
                <div class="shop-info">
                    <h3>Shop Information Retrieved:</h3>
                    <p><strong>Shop Name:</strong> {shop_info.get('name', 'N/A')}</p>
                    <p><strong>Email:</strong> {shop_info.get('email', 'N/A')}</p>
                    <p><strong>Domain:</strong> {shop_info.get('domain', 'N/A')}</p>
                </div>
                
                <div class="token">
                    <strong>Access Token:</strong> {access_token[:20]}...{access_token[-10:]}
                </div>
                
                <p><strong>Your Agentix Chat Bot is now connected and ready to use!</strong></p>
                
                <a href="https://{shop}/admin/apps" class="btn">Go to Apps</a>
                <a href="http://localhost:8000/api/v1/shops/{shop}/info" class="btn">Test API</a>
                
                <script>
                    // Auto-redirect after 5 seconds
                    setTimeout(() => {{
                        if (confirm("Redirect to Shopify admin?")) {{
                            window.location.href = 'https://{shop}/admin/apps';
                        }}
                    }}, 5000);
                </script>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=success_html)
        
    except Exception as e:
        error_html = f"""
        <html><body style="font-family: Arial, sans-serif; text-align: center; margin-top: 50px;">
            <h1 style="color: red;">❌ Installation Failed</h1>
            <p><strong>Error:</strong> {str(e)}</p>
            <p><strong>Shop:</strong> {shop}</p>
            <a href="https://{shop}/admin">Return to Admin</a>
        </body></html>
        """
        return HTMLResponse(content=error_html, status_code=500)

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
            raise Exception(f"Token exchange failed: {response.text}")
        
        return response.json()

async def test_api_call(shop_domain: str, access_token: str) -> dict:
    """Test API call to verify token works."""
    api_url = f"https://{shop_domain}/admin/api/2023-10/shop.json"
    
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(api_url, headers=headers, timeout=30.0)
        
        if response.status_code == 200:
            return response.json().get("shop", {})
        else:
            return {"error": f"API test failed: {response.status_code}"}

@app.get("/api/v1/shops")
async def list_installed_shops():
    """List all shops with installed tokens."""
    return {
        "installed_shops": [
            {
                "shop": shop,
                "installed_at": data["installed_at"],
                "scope": data["scope"]
            }
            for shop, data in access_tokens.items()
        ],
        "total_installations": len(access_tokens)
    }

@app.get("/api/v1/shops/{shop_domain}/info")
async def get_shop_info(shop_domain: str):
    """Get shop information using stored access token."""
    if shop_domain not in access_tokens:
        raise HTTPException(status_code=404, detail="Shop not found or not installed")
    
    access_token = access_tokens[shop_domain]["access_token"]
    
    try:
        shop_info = await test_api_call(shop_domain, access_token)
        return {
            "shop": shop_domain,
            "info": shop_info,
            "token_status": "valid"
        }
    except Exception as e:
        return {
            "shop": shop_domain,
            "error": str(e),
            "token_status": "invalid"
        }

@app.post("/api/v1/shops/{shop_domain}/orders")
async def get_orders(shop_domain: str, limit: int = 10):
    """Get orders from shop using stored access token."""
    if shop_domain not in access_tokens:
        raise HTTPException(status_code=404, detail="Shop not found")
    
    access_token = access_tokens[shop_domain]["access_token"]
    api_url = f"https://{shop_domain}/admin/api/2023-10/orders.json?limit={limit}"
    
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient() as client:
        response = await client.get(api_url, headers=headers, timeout=30.0)
        
        if response.status_code == 200:
            return response.json()
        else:
            raise HTTPException(status_code=response.status_code, detail=response.text)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)