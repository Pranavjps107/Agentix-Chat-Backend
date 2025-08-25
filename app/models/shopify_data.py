# app/models/shopify_data.py
"""
Shopify data models for storing products, customers, orders, etc.
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Numeric, ForeignKey, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from pydantic import BaseModel, validator
from app.models.database import Base
from decimal import Decimal


class ShopifyShop(Base):
    """Store shop information."""
    __tablename__ = "shopify_shops"
    
    id = Column(Integer, primary_key=True, index=True)
    shop_domain = Column(String(255), unique=True, index=True, nullable=False)
    shopify_shop_id = Column(String(50), index=True)
    name = Column(String(255))
    email = Column(String(255))
    domain = Column(String(255))
    currency = Column(String(10))
    timezone = Column(String(100))
    country = Column(String(100))
    phone = Column(String(50))
    address = Column(JSON)
    plan_name = Column(String(100))
    shop_data = Column(JSON)  # Raw shop data from Shopify
    last_synced = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    products = relationship("ShopifyProduct", back_populates="shop")
    customers = relationship("ShopifyCustomer", back_populates="shop")
    orders = relationship("ShopifyOrder", back_populates="shop")


class ShopifyProduct(Base):
    """Store product information."""
    __tablename__ = "shopify_products"
    
    id = Column(Integer, primary_key=True, index=True)
    shop_domain = Column(String(255), ForeignKey("shopify_shops.shop_domain"), index=True)
    shopify_product_id = Column(String(50), index=True, nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    handle = Column(String(255), index=True)
    vendor = Column(String(255), index=True)
    product_type = Column(String(255), index=True)
    status = Column(String(50), index=True)  # active, archived, draft
    tags = Column(JSON)  # Array of tags
    images = Column(JSON)  # Array of image URLs
    options = Column(JSON)  # Product options (size, color, etc.)
    seo_title = Column(String(255))
    seo_description = Column(Text)
    published_at = Column(DateTime(timezone=True))
    created_at_shopify = Column(DateTime(timezone=True))
    updated_at_shopify = Column(DateTime(timezone=True))
    last_synced = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    shop = relationship("ShopifyShop", back_populates="products")
    variants = relationship("ShopifyProductVariant", back_populates="product")
    order_line_items = relationship("ShopifyOrderLineItem", back_populates="product")


class ShopifyProductVariant(Base):
    """Store product variant information."""
    __tablename__ = "shopify_product_variants"
    
    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("shopify_products.id"), index=True)
    shop_domain = Column(String(255), index=True)
    shopify_variant_id = Column(String(50), index=True, nullable=False)
    shopify_product_id = Column(String(50), index=True)
    title = Column(String(255))
    price = Column(Numeric(10, 2))
    compare_at_price = Column(Numeric(10, 2))
    sku = Column(String(255), index=True)
    barcode = Column(String(255))
    inventory_quantity = Column(Integer, default=0)
    inventory_policy = Column(String(50))  # deny, continue
    inventory_management = Column(String(50))  # shopify, not_managed
    weight = Column(Numeric(8, 2))
    weight_unit = Column(String(20))
    requires_shipping = Column(Boolean, default=True)
    taxable = Column(Boolean, default=True)
    option1 = Column(String(255))
    option2 = Column(String(255))
    option3 = Column(String(255))
    image_id = Column(String(50))
    available = Column(Boolean, default=True)
    last_synced = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    product = relationship("ShopifyProduct", back_populates="variants")


class ShopifyCustomer(Base):
    """Store customer information."""
    __tablename__ = "shopify_customers"
    
    id = Column(Integer, primary_key=True, index=True)
    shop_domain = Column(String(255), ForeignKey("shopify_shops.shop_domain"), index=True)
    shopify_customer_id = Column(String(50), index=True, nullable=False)
    email = Column(String(255), index=True)
    first_name = Column(String(255))
    last_name = Column(String(255))
    phone = Column(String(50))
    accepts_marketing = Column(Boolean, default=False)
    orders_count = Column(Integer, default=0)
    total_spent = Column(Numeric(12, 2), default=0)
    state = Column(String(50), index=True)  # disabled, invited, enabled, declined
    verified_email = Column(Boolean, default=False)
    tax_exempt = Column(Boolean, default=False)
    tags = Column(JSON)
    addresses = Column(JSON)  # Array of addresses
    default_address = Column(JSON)
    customer_data = Column(JSON)  # Additional customer data
    created_at_shopify = Column(DateTime(timezone=True))
    updated_at_shopify = Column(DateTime(timezone=True))
    last_synced = Column(DateTime(timezone=True))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    shop = relationship("ShopifyShop", back_populates="customers")
    orders = relationship("ShopifyOrder", back_populates="customer")


class ShopifyOrder(Base):
    """Store order information."""
    __tablename__ = "shopify_orders"
    
    id = Column(Integer, primary_key=True, index=True)
    shop_domain = Column(String(255), ForeignKey("shopify_shops.shop_domain"), index=True)
    customer_id = Column(Integer, ForeignKey("shopify_customers.id"), nullable=True, index=True)
    shopify_order_id = Column(String(50), index=True, nullable=False)
    shopify_customer_id = Column(String(50), index=True)
    order_number = Column(String(50), index=True)
    name = Column(String(50), index=True)  # #1001, #1002, etc.
    email = Column(String(255), index=True)
    phone = Column(String(50))
    
    # Order amounts
    total_price = Column(Numeric(12, 2))
    subtotal_price = Column(Numeric(12, 2))
    total_tax = Column(Numeric(12, 2))
    total_discounts = Column(Numeric(12, 2))
    total_shipping = Column(Numeric(12, 2))
    currency = Column(String(10))
    
    # Order status
    financial_status = Column(String(50), index=True)  # pending, authorized, paid, refunded, etc.
    fulfillment_status = Column(String(50), index=True)  # fulfilled, partial, unfulfilled
    order_status_url = Column(Text)
    cancel_reason = Column(String(100))
    cancelled_at = Column(DateTime(timezone=True))
    
    # Addresses
    billing_address = Column(JSON)
    shipping_address = Column(JSON)
    
    # Shipping and fulfillment
    shipping_lines = Column(JSON)
    fulfillments = Column(JSON)
    tracking_numbers = Column(JSON)
    tracking_urls = Column(JSON)
    
    # Payments
    payment_details = Column(JSON)
    payment_gateway_names = Column(JSON)
    
    # Additional data
    tags = Column(JSON)
    note = Column(Text)
    note_attributes = Column(JSON)
    discount_codes = Column(JSON)
    tax_lines = Column(JSON)
    
    # Timestamps
    created_at_shopify = Column(DateTime(timezone=True))
    updated_at_shopify = Column(DateTime(timezone=True))
    processed_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))
    last_synced = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    shop = relationship("ShopifyShop", back_populates="orders")
    customer = relationship("ShopifyCustomer", back_populates="orders")
    line_items = relationship("ShopifyOrderLineItem", back_populates="order")


class ShopifyOrderLineItem(Base):
    """Store order line item information."""
    __tablename__ = "shopify_order_line_items"
    
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("shopify_orders.id"), index=True)
    product_id = Column(Integer, ForeignKey("shopify_products.id"), nullable=True, index=True)
    shop_domain = Column(String(255), index=True)
    shopify_line_item_id = Column(String(50), index=True)
    shopify_order_id = Column(String(50), index=True)
    shopify_product_id = Column(String(50), index=True)
    shopify_variant_id = Column(String(50), index=True)
    
    title = Column(String(500))
    name = Column(String(500))  # Product title + variant title
    variant_title = Column(String(255))
    sku = Column(String(255))
    vendor = Column(String(255))
    product_type = Column(String(255))
    
    quantity = Column(Integer)
    price = Column(Numeric(10, 2))
    total_discount = Column(Numeric(10, 2))
    
    fulfillment_service = Column(String(100))
    fulfillment_status = Column(String(50))
    
    properties = Column(JSON)  # Custom properties
    tax_lines = Column(JSON)
    discount_allocations = Column(JSON)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    order = relationship("ShopifyOrder", back_populates="line_items")
    product = relationship("ShopifyProduct", back_populates="order_line_items")


class ShopifySyncLog(Base):
    """Track synchronization operations."""
    __tablename__ = "shopify_sync_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    shop_domain = Column(String(255), index=True, nullable=False)
    sync_type = Column(String(50), index=True, nullable=False)  # products, orders, customers, etc.
    status = Column(String(50), index=True, nullable=False)  # success, error, in_progress
    records_processed = Column(Integer, default=0)
    records_created = Column(Integer, default=0)
    records_updated = Column(Integer, default=0)
    records_failed = Column(Integer, default=0)
    error_message = Column(Text)
    start_time = Column(DateTime(timezone=True))
    end_time = Column(DateTime(timezone=True))
    duration_seconds = Column(Integer)
    last_cursor = Column(String(255))  # For pagination
    sync_metadata = Column(JSON)  # Additional sync information
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# Pydantic models for API responses
class ShopifyProductResponse(BaseModel):
    """Response model for product data."""
    id: int
    shopify_product_id: str
    title: str
    description: Optional[str]
    handle: str
    vendor: Optional[str]
    product_type: Optional[str]
    status: str
    tags: Optional[List[str]]
    images: Optional[List[dict]]
    variants: List[dict]
    created_at: datetime
    updated_at: datetime

class ShopifyOrderResponse(BaseModel):
    """Response model for order data."""
    id: int
    shopify_order_id: str
    order_number: str
    name: str
    email: Optional[str]
    total_price: Decimal
    financial_status: str
    fulfillment_status: str
    customer: Optional[dict]
    line_items: List[dict]
    created_at: datetime
    updated_at: datetime

class ShopifyCustomerResponse(BaseModel):
    """Response model for customer data."""
    id: int
    shopify_customer_id: str
    email: Optional[str]
    first_name: Optional[str]
    last_name: Optional[str]
    orders_count: int
    total_spent: Decimal
    created_at: datetime
    updated_at: datetime

class SyncStatusResponse(BaseModel):
    """Response model for sync status."""
    sync_type: str
    status: str
    records_processed: int
    last_sync: Optional[datetime]
    next_sync: Optional[datetime]