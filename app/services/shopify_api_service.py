# app/services/shopify_api_service.py
"""
Comprehensive Shopify API service for fetching and managing store data.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
import httpx
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.core.config import settings
from app.core.logging import logger
from app.models.auth import ShopifyAuth
from app.models.shopify_data import (
    ShopifyShop, ShopifyProduct, ShopifyProductVariant, 
    ShopifyCustomer, ShopifyOrder, ShopifyOrderLineItem,
    ShopifySyncLog
)
from decimal import Decimal


class ShopifyAPIService:
    """Service for interacting with Shopify GraphQL API."""
    
    def __init__(self):
        self.api_version = "2024-10"
        self.base_url = "https://{shop_domain}/admin/api/{version}/graphql.json"
        self.timeout = 30.0
        
    async def _make_graphql_request(
        self, 
        shop_domain: str, 
        access_token: str, 
        query: str, 
        variables: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """Make a GraphQL request to Shopify API."""
        url = self.base_url.format(shop_domain=shop_domain, version=self.api_version)
        
        headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }
        
        payload = {
            "query": query,
            "variables": variables or {}
        }
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            try:
                response = await client.post(url, json=payload, headers=headers)
                
                if response.status_code != 200:
                    logger.error(f"API request failed: {response.status_code} - {response.text}")
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Shopify API request failed: {response.text}"
                    )
                
                data = response.json()
                
                if "errors" in data:
                    logger.error(f"GraphQL errors: {data['errors']}")
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"GraphQL errors: {data['errors']}"
                    )
                
                return data
                
            except httpx.TimeoutException:
                logger.error(f"API request timeout for shop: {shop_domain}")
                raise HTTPException(
                    status_code=status.HTTP_408_REQUEST_TIMEOUT,
                    detail="Shopify API request timed out"
                )
    
    async def get_shop_info(self, shop_domain: str, access_token: str) -> Dict[str, Any]:
        """Fetch shop information."""
        query = """
        query getShop {
            shop {
                id
                name
                email
                myshopifyDomain
                primaryDomain {
                    host
                }
                currencyCode
                timezoneAbbreviation
                ianaTimezone
                contactEmail
                customerEmail
                phone
                address1
                address2
                city
                province
                country
                countryCode
                zip
                plan {
                    displayName
                    partnerDevelopment
                    shopifyPlus
                }
                features {
                    storefront
                    multiLocation
                    mobileStorefront
                }
            }
        }
        """
        
        response = await self._make_graphql_request(shop_domain, access_token, query)
        return response.get("data", {}).get("shop", {})
    
    async def get_products(
        self, 
        shop_domain: str, 
        access_token: str, 
        limit: int = 50,
        cursor: Optional[str] = None,
        query_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch products with variants."""
        variables = {"first": limit}
        
        if cursor:
            variables["after"] = cursor
            
        if query_filter:
            variables["query"] = query_filter
        
        query = """
        query getProducts($first: Int!, $after: String, $query: String) {
            products(first: $first, after: $after, query: $query) {
                pageInfo {
                    hasNextPage
                    hasPreviousPage
                    startCursor
                    endCursor
                }
                edges {
                    cursor
                    node {
                        id
                        title
                        description
                        handle
                        vendor
                        productType
                        status
                        tags
                        images(first: 10) {
                            edges {
                                node {
                                    id
                                    url
                                    altText
                                    width
                                    height
                                }
                            }
                        }
                        variants(first: 100) {
                            edges {
                                node {
                                    id
                                    title
                                    price
                                    compareAtPrice
                                    sku
                                    barcode
                                    inventoryQuantity
                                    inventoryPolicy
                                    inventoryManagement
                                    weight
                                    weightUnit
                                    requiresShipping
                                    taxable
                                    selectedOptions {
                                        name
                                        value
                                    }
                                    image {
                                        id
                                        url
                                    }
                                    availableForSale
                                }
                            }
                        }
                        seo {
                            title
                            description
                        }
                        options {
                            id
                            name
                            values
                            position
                        }
                        publishedAt
                        createdAt
                        updatedAt
                    }
                }
            }
        }
        """
        
        response = await self._make_graphql_request(shop_domain, access_token, query, variables)
        return response.get("data", {}).get("products", {})
    
    async def get_orders(
        self,
        shop_domain: str,
        access_token: str,
        limit: int = 50,
        cursor: Optional[str] = None,
        query_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch orders with line items."""
        variables = {"first": limit}
        
        if cursor:
            variables["after"] = cursor
            
        if query_filter:
            variables["query"] = query_filter
        
        query = """
        query getOrders($first: Int!, $after: String, $query: String) {
            orders(first: $first, after: $after, query: $query) {
                pageInfo {
                    hasNextPage
                    hasPreviousPage
                    startCursor
                    endCursor
                }
                edges {
                    cursor
                    node {
                        id
                        name
                        orderNumber
                        email
                        phone
                        totalPriceSet {
                            shopMoney {
                                amount
                                currencyCode
                            }
                        }
                        subtotalPriceSet {
                            shopMoney {
                                amount
                                currencyCode
                            }
                        }
                        totalTaxSet {
                            shopMoney {
                                amount
                                currencyCode
                            }
                        }
                        totalDiscountsSet {
                            shopMoney {
                                amount
                                currencyCode
                            }
                        }
                        totalShippingPriceSet {
                            shopMoney {
                                amount
                                currencyCode
                            }
                        }
                        financialStatus
                        fulfillmentStatus
                        customer {
                            id
                            email
                            firstName
                            lastName
                            phone
                            ordersCount
                            totalSpentV2 {
                                amount
                                currencyCode
                            }
                        }
                        billingAddress {
                            firstName
                            lastName
                            company
                            address1
                            address2
                            city
                            province
                            country
                            zip
                            phone
                        }
                        shippingAddress {
                            firstName
                            lastName
                            company
                            address1
                            address2
                            city
                            province
                            country
                            zip
                            phone
                        }
                        lineItems(first: 100) {
                            edges {
                                node {
                                    id
                                    title
                                    name
                                    variantTitle
                                    sku
                                    vendor
                                    productType
                                    quantity
                                    originalUnitPriceSet {
                                        shopMoney {
                                            amount
                                            currencyCode
                                        }
                                    }
                                    totalDiscountSet {
                                        shopMoney {
                                            amount
                                            currencyCode
                                        }
                                    }
                                    fulfillmentService {
                                        serviceName
                                    }
                                    fulfillmentStatus
                                    product {
                                        id
                                        handle
                                    }
                                    variant {
                                        id
                                        sku
                                        title
                                    }
                                    customAttributes {
                                        key
                                        value
                                    }
                                    taxLines {
                                        title
                                        priceSet {
                                            shopMoney {
                                                amount
                                                currencyCode
                                            }
                                        }
                                        rate
                                        ratePercentage
                                    }
                                }
                            }
                        }
                        shippingLines(first: 10) {
                            edges {
                                node {
                                    title
                                    originalPriceSet {
                                        shopMoney {
                                            amount
                                            currencyCode
                                        }
                                    }
                                    carrierIdentifier
                                    code
                                }
                            }
                        }
                        fulfillments(first: 10) {
                            trackingInfo {
                                number
                                url
                                company
                            }
                            status
                            updatedAt
                        }
                        tags
                        note
                        customAttributes {
                            key
                            value
                        }
                        discountCodes
                        createdAt
                        updatedAt
                        processedAt
                        closedAt
                        cancelledAt
                        cancelReason
                    }
                }
            }
        }
        """
        
        response = await self._make_graphql_request(shop_domain, access_token, query, variables)
        return response.get("data", {}).get("orders", {})
    
    async def get_customers(
        self,
        shop_domain: str,
        access_token: str,
        limit: int = 50,
        cursor: Optional[str] = None,
        query_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch customers."""
        variables = {"first": limit}
        
        if cursor:
            variables["after"] = cursor
            
        if query_filter:
            variables["query"] = query_filter
        
        query = """
        query getCustomers($first: Int!, $after: String, $query: String) {
            customers(first: $first, after: $after, query: $query) {
                pageInfo {
                    hasNextPage
                    hasPreviousPage
                    startCursor
                    endCursor
                }
                edges {
                    cursor
                    node {
                        id
                        email
                        firstName
                        lastName
                        phone
                        acceptsMarketing
                        ordersCount
                        totalSpentV2 {
                            amount
                            currencyCode
                        }
                        state
                        verifiedEmail
                        taxExempt
                        tags
                        addresses(first: 10) {
                            firstName
                            lastName
                            company
                            address1
                            address2
                            city
                            province
                            country
                            zip
                            phone
                            provinceCode
                            countryCodeV2
                        }
                        defaultAddress {
                            firstName
                            lastName
                            company
                            address1
                            address2
                            city
                            province
                            country
                            zip
                            phone
                        }
                        createdAt
                        updatedAt
                    }
                }
            }
        }
        """
        
        response = await self._make_graphql_request(shop_domain, access_token, query, variables)
        return response.get("data", {}).get("customers", {})


# Global service instance
shopify_api_service = ShopifyAPIService()