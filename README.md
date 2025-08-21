# Shopify Authentication Service

A production-ready FastAPI backend service for handling Shopify OAuth 2.0 authentication flow.

## Features

- **Secure OAuth 2.0 Flow**: Complete implementation of Shopify's authorization code grant
- **Token Management**: Secure storage and retrieval of access tokens
- **Webhook Verification**: HMAC signature verification for Shopify webhooks
- **Database Integration**: PostgreSQL with Supabase support
- **Comprehensive Testing**: Unit tests with high coverage
- **Production Ready**: Docker containerization, logging, error handling
- **Type Safety**: Full type hints with Pydantic validation

## Quick Start

### Prerequisites

- Python 3.9+
- PostgreSQL (or Supabase)
- Docker & Docker Compose (optional)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd shopify-auth-backend