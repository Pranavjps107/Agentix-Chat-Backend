"""
Script to validate Shopify configuration before running the app.
"""
import os
from dotenv import load_dotenv

def validate_shopify_config():
    """Validate Shopify configuration."""
    load_dotenv()
    
    print("🔍 Validating Shopify Configuration...")
    
    # Required variables
    required_vars = {
        "SHOPIFY_CLIENT_ID": "Client ID from Shopify Partners Dashboard",
        "SHOPIFY_CLIENT_SECRET": "Client Secret from Shopify Partners Dashboard",
        "SHOPIFY_REDIRECT_URI": "Redirect URI (should match Partners Dashboard)",
        "DATABASE_URL": "Supabase Database URL"
    }
    
    errors = []
    warnings = []
    
    for var, description in required_vars.items():
        value = os.getenv(var)
        
        if not value:
            errors.append(f"❌ {var} is missing ({description})")
        elif var == "SHOPIFY_CLIENT_ID":
            if value == "test" or len(value) < 10:
                errors.append(f"❌ {var} appears to be a test value. Use real Client ID: 5c3cdab58e82a4d5bb")
            else:
                print(f"✅ {var}: {value}")
        elif var == "SHOPIFY_CLIENT_SECRET":
            if value == "test" or len(value) < 20:
                errors.append(f"❌ {var} appears to be a test value. Use real Client Secret from Partners Dashboard")
            else:
                print(f"✅ {var}: {'*' * (len(value) - 4) + value[-4:]}")
        else:
            print(f"✅ {var}: {value}")
    
    # Check redirect URI
    redirect_uri = os.getenv("SHOPIFY_REDIRECT_URI")
    if redirect_uri and "localhost:8000" in redirect_uri:
        print(f"⚠️  Using localhost redirect URI (OK for development)")
    
    # Check scopes
    scopes = os.getenv("SHOPIFY_SCOPES", "")
    if scopes:
        scope_list = [s.strip() for s in scopes.split(",")]
        print(f"✅ SHOPIFY_SCOPES: {scope_list}")
    
    # Print results
    if errors:
        print("\n🚨 CONFIGURATION ERRORS:")
        for error in errors:
            print(error)
        print("\n📋 TO FIX:")
        print("1. Copy your real Client ID from Shopify Partners Dashboard: 5c3cdab58e82a4d5bb")
        print("2. Copy your real Client Secret from Shopify Partners Dashboard")
        print("3. Update your .env file with these real values")
        return False
    else:
        print("\n✅ Configuration looks good!")
        return True

if __name__ == "__main__":
    validate_shopify_config()