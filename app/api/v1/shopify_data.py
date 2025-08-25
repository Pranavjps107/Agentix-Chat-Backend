# app/api/v1/shopify_data.py
"""
API routes for accessing synchronized Shopify data.
"""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_, func, String, cast, text
from app.models.database import get_db
from app.models.shopify_data import (
    ShopifyShop, ShopifyProduct, ShopifyProductVariant,
    ShopifyCustomer, ShopifyOrder, ShopifyOrderLineItem,
    ShopifySyncLog, ShopifyProductResponse, ShopifyOrderResponse,
    ShopifyCustomerResponse, SyncStatusResponse
)
from app.services.shopify_sync_service import shopify_sync_service
from app.core.logging import logger
from datetime import datetime, timedelta

router = APIRouter(prefix="/shopify", tags=["shopify-data"])


# ============================================================================
# SYNC ENDPOINTS
# ============================================================================

@router.post(
    "/sync/{shop_domain}/full",
    summary="Trigger full data synchronization",
    description="Start full synchronization of all Shopify data for a shop"
)
async def trigger_full_sync(
    shop_domain: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Trigger full synchronization in background."""
    try:
        # Add sync task to background
        background_tasks.add_task(
            shopify_sync_service.full_sync,
            db, shop_domain
        )
        
        return {
            "message": "Full synchronization started",
            "shop_domain": shop_domain,
            "status": "in_progress"
        }
    except Exception as e:
        logger.error(f"Error starting full sync for {shop_domain}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start synchronization"
        )


@router.post(
    "/sync/{shop_domain}/products",
    summary="Sync products only",
    description="Synchronize only products and variants"
)
async def sync_products_only(
    shop_domain: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Sync products in background."""
    try:
        background_tasks.add_task(
            shopify_sync_service.sync_products,
            db, shop_domain
        )
        
        return {
            "message": "Products synchronization started",
            "shop_domain": shop_domain,
            "status": "in_progress"
        }
    except Exception as e:
        logger.error(f"Error starting products sync for {shop_domain}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start products synchronization"
        )


@router.post(
    "/sync/{shop_domain}/orders",
    summary="Sync orders only",
    description="Synchronize only orders"
)
async def sync_orders_only(
    shop_domain: str,
    days_back: int = Query(30, description="Number of days back to sync"),
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Sync orders in background."""
    try:
        background_tasks.add_task(
            shopify_sync_service.sync_orders,
            db, shop_domain, days_back
        )
        
        return {
            "message": "Orders synchronization started",
            "shop_domain": shop_domain,
            "days_back": days_back,
            "status": "in_progress"
        }
    except Exception as e:
        logger.error(f"Error starting orders sync for {shop_domain}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start orders synchronization"
        )


@router.post(
    "/sync/{shop_domain}/customers",
    summary="Sync customers only",
    description="Synchronize only customers"
)
async def sync_customers_only(
    shop_domain: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """Sync customers in background."""
    try:
        background_tasks.add_task(
            shopify_sync_service.sync_customers,
            db, shop_domain
        )
        
        return {
            "message": "Customers synchronization started",
            "shop_domain": shop_domain,
            "status": "in_progress"
        }
    except Exception as e:
        logger.error(f"Error starting customers sync for {shop_domain}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to start customers synchronization"
        )


@router.get(
    "/sync/{shop_domain}/status",
    response_model=List[SyncStatusResponse],
    summary="Get synchronization status",
    description="Get current synchronization status for all data types"
)
async def get_sync_status(
    shop_domain: str,
    db: Session = Depends(get_db)
):
    """Get synchronization status for all data types."""
    try:
        sync_types = ["products", "orders", "customers"]
        statuses = []
        
        for sync_type in sync_types:
            latest_sync = db.query(ShopifySyncLog).filter(
                and_(
                    ShopifySyncLog.shop_domain == shop_domain,
                    ShopifySyncLog.sync_type == sync_type
                )
            ).order_by(desc(ShopifySyncLog.created_at)).first()
            
            if latest_sync:
                statuses.append(SyncStatusResponse(
                    sync_type=sync_type,
                    status=latest_sync.status,
                    records_processed=latest_sync.records_processed,
                    last_sync=latest_sync.created_at,
                    next_sync=None  # Could implement scheduled sync logic here
                ))
            else:
                statuses.append(SyncStatusResponse(
                    sync_type=sync_type,
                    status="never_synced",
                    records_processed=0,
                    last_sync=None,
                    next_sync=None
                ))
        
        return statuses
        
    except Exception as e:
        logger.error(f"Error getting sync status for {shop_domain}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get synchronization status"
        )

# ============================================================================
# PRODUCTS ENDPOINTS
# ============================================================================

@router.get(
    "/shops/{shop_domain}/products",
    response_model=List[ShopifyProductResponse],
    summary="Get products",
    description="Get all products for a shop with filtering and pagination"
)

async def get_products(
    shop_domain: str,
    skip: int = Query(0, ge=0, description="Number of products to skip"),
    limit: int = Query(50, ge=1, le=100, description="Number of products to return"),
    search: Optional[str] = Query(None, description="Search in title and description"),
    status: Optional[str] = Query(None, description="Filter by status"),
    vendor: Optional[str] = Query(None, description="Filter by vendor"),
    product_type: Optional[str] = Query(None, description="Filter by product type"),
    db: Session = Depends(get_db)
):
    """Get products with filtering and search."""
    try:
        query = db.query(ShopifyProduct).filter(
            and_(
                ShopifyProduct.shop_domain == shop_domain,
                ShopifyProduct.is_active == True
            )
        )
        
        # Apply filters
        if search:
            search_conditions = [
                ShopifyProduct.title.ilike(f"%{search}%"),
                ShopifyProduct.description.ilike(f"%{search}%")
            ]
            
            # Safe tag search - handle different database types
            try:
                # Try JSONB operator first (PostgreSQL)
                search_conditions.append(
                    ShopifyProduct.tags.op('?|')(f'{{"{search}"}}'::jsonb)
                )
            except Exception:
                try:
                    # Fallback to casting as text
                    search_conditions.append(
                        func.cast(ShopifyProduct.tags, String).ilike(f'%{search}%')
                    )
                except Exception:
                    # If all else fails, skip tag search
                    pass
            
            query = query.filter(or_(*search_conditions))
        
        if status:
            query = query.filter(ShopifyProduct.status == status.lower())
        
        if vendor:
            query = query.filter(ShopifyProduct.vendor.ilike(f"%{vendor}%"))
        
        if product_type:
            query = query.filter(ShopifyProduct.product_type.ilike(f"%{product_type}%"))
        
        # Get total count
        total_count = query.count()
        
        # Apply pagination and ordering
        products = query.order_by(desc(ShopifyProduct.updated_at)).offset(skip).limit(limit).all()
        
        # Convert to response format
        response_products = []
        for product in products:
            variants = db.query(ShopifyProductVariant).filter(
                ShopifyProductVariant.product_id == product.id
            ).all()
            
            response_products.append(ShopifyProductResponse(
                id=product.id,
                shopify_product_id=product.shopify_product_id,
                title=product.title,
                description=product.description,
                handle=product.handle,
                vendor=product.vendor,
                product_type=product.product_type,
                status=product.status,
                tags=product.tags or [],
                images=product.images or [],
                variants=[{
                    "id": v.id,
                    "shopify_variant_id": v.shopify_variant_id,
                    "title": v.title,
                    "price": float(v.price) if v.price else 0,
                    "compare_at_price": float(v.compare_at_price) if v.compare_at_price else None,
                    "sku": v.sku,
                    "inventory_quantity": v.inventory_quantity,
                    "available": v.available
                } for v in variants],
                created_at=product.created_at,
                updated_at=product.updated_at
            ))
        
        return response_products
        
    except Exception as e:
        logger.error(f"Error getting products for {shop_domain}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get products"
        )

@router.get(
    "/shops/{shop_domain}/products/{product_id}",
    response_model=ShopifyProductResponse,
    summary="Get single product",
    description="Get detailed information about a specific product"
)
async def get_product(
    shop_domain: str,
    product_id: int,
    db: Session = Depends(get_db)
):
    """Get a single product with all its details."""
    try:
        product = db.query(ShopifyProduct).filter(
            and_(
                ShopifyProduct.shop_domain == shop_domain,
                ShopifyProduct.id == product_id,
                ShopifyProduct.is_active == True
            )
        ).first()
        
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Product not found"
            )
        
        # Get variants
        variants = db.query(ShopifyProductVariant).filter(
            ShopifyProductVariant.product_id == product.id
        ).all()
        
        return ShopifyProductResponse(
            id=product.id,
            shopify_product_id=product.shopify_product_id,
            title=product.title,
            description=product.description,
            handle=product.handle,
            vendor=product.vendor,
            product_type=product.product_type,
            status=product.status,
            tags=product.tags or [],
            images=product.images or [],
            variants=[{
                "id": v.id,
                "shopify_variant_id": v.shopify_variant_id,
                "title": v.title,
                "price": float(v.price) if v.price else 0,
                "compare_at_price": float(v.compare_at_price) if v.compare_at_price else None,
                "sku": v.sku,
                "barcode": v.barcode,
                "inventory_quantity": v.inventory_quantity,
                "weight": float(v.weight) if v.weight else None,
                "weight_unit": v.weight_unit,
                "available": v.available,
                "option1": v.option1,
                "option2": v.option2,
                "option3": v.option3
            } for v in variants],
            created_at=product.created_at,
            updated_at=product.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting product {product_id} for {shop_domain}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get product"
        )


# ============================================================================
# ORDERS ENDPOINTS
# ============================================================================

@router.get(
    "/shops/{shop_domain}/orders",
    response_model=List[ShopifyOrderResponse],
    summary="Get orders",
    description="Get orders for a shop with filtering and pagination"
)
async def get_orders(
    shop_domain: str,
    skip: int = Query(0, ge=0, description="Number of orders to skip"),
    limit: int = Query(50, ge=1, le=100, description="Number of orders to return"),
    financial_status: Optional[str] = Query(None, description="Filter by financial status"),
    fulfillment_status: Optional[str] = Query(None, description="Filter by fulfillment status"),
    customer_email: Optional[str] = Query(None, description="Filter by customer email"),
    from_date: Optional[datetime] = Query(None, description="Orders from this date"),
    to_date: Optional[datetime] = Query(None, description="Orders until this date"),
    db: Session = Depends(get_db)
):
    """Get orders with filtering."""
    try:
        query = db.query(ShopifyOrder).filter(
            ShopifyOrder.shop_domain == shop_domain
        )
        
        # Apply filters
        if financial_status:
            query = query.filter(ShopifyOrder.financial_status == financial_status.lower())
        
        if fulfillment_status:
            query = query.filter(ShopifyOrder.fulfillment_status == fulfillment_status.lower())
        
        if customer_email:
            query = query.filter(ShopifyOrder.email.ilike(f"%{customer_email}%"))
        
        if from_date:
            query = query.filter(ShopifyOrder.created_at_shopify >= from_date)
        
        if to_date:
            query = query.filter(ShopifyOrder.created_at_shopify <= to_date)
        
        # Apply pagination and ordering
        orders = query.order_by(desc(ShopifyOrder.created_at_shopify)).offset(skip).limit(limit).all()
        
        # Convert to response format
        response_orders = []
        for order in orders:
            # Get customer info
            customer_data = None
            if order.customer_id:
                customer = db.query(ShopifyCustomer).filter(
                    ShopifyCustomer.id == order.customer_id
                ).first()
                if customer:
                    customer_data = {
                        "id": customer.id,
                        "email": customer.email,
                        "first_name": customer.first_name,
                        "last_name": customer.last_name,
                        "orders_count": customer.orders_count,
                        "total_spent": float(customer.total_spent) if customer.total_spent else 0
                    }
            
            # Get line items
            line_items = db.query(ShopifyOrderLineItem).filter(
                ShopifyOrderLineItem.order_id == order.id
            ).all()
            
            response_orders.append(ShopifyOrderResponse(
                id=order.id,
                shopify_order_id=order.shopify_order_id,
                order_number=order.order_number,
                name=order.name,
                email=order.email,
                total_price=order.total_price,
                financial_status=order.financial_status,
                fulfillment_status=order.fulfillment_status,
                customer=customer_data,
                line_items=[{
                    "id": item.id,
                    "title": item.title,
                    "quantity": item.quantity,
                    "price": float(item.price) if item.price else 0,
                    "sku": item.sku,
                    "vendor": item.vendor
                } for item in line_items],
                created_at=order.created_at,
                updated_at=order.updated_at
            ))
        
        return response_orders
        
    except Exception as e:
        logger.error(f"Error getting orders for {shop_domain}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get orders"
        )


@router.get(
    "/shops/{shop_domain}/orders/{order_id}",
    response_model=ShopifyOrderResponse,
    summary="Get single order",
    description="Get detailed information about a specific order"
)
async def get_order(
    shop_domain: str,
    order_id: int,
    db: Session = Depends(get_db)
):
    """Get a single order with all its details."""
    try:
        order = db.query(ShopifyOrder).filter(
            and_(
                ShopifyOrder.shop_domain == shop_domain,
                ShopifyOrder.id == order_id
            )
        ).first()
        
        if not order:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Order not found"
            )
        
        # Get customer info
        customer_data = None
        if order.customer_id:
            customer = db.query(ShopifyCustomer).filter(
                ShopifyCustomer.id == order.customer_id
            ).first()
            if customer:
                customer_data = {
                    "id": customer.id,
                    "email": customer.email,
                    "first_name": customer.first_name,
                    "last_name": customer.last_name,
                    "phone": customer.phone,
                    "orders_count": customer.orders_count,
                    "total_spent": float(customer.total_spent) if customer.total_spent else 0
                }
        
        # Get line items
        line_items = db.query(ShopifyOrderLineItem).filter(
            ShopifyOrderLineItem.order_id == order.id
        ).all()
        
        return ShopifyOrderResponse(
            id=order.id,
            shopify_order_id=order.shopify_order_id,
            order_number=order.order_number,
            name=order.name,
            email=order.email,
            total_price=order.total_price,
            financial_status=order.financial_status,
            fulfillment_status=order.fulfillment_status,
            customer=customer_data,
            line_items=[{
                "id": item.id,
                "title": item.title,
                "name": item.name,
                "quantity": item.quantity,
                "price": float(item.price) if item.price else 0,
                "total_discount": float(item.total_discount) if item.total_discount else 0,
                "sku": item.sku,
                "vendor": item.vendor,
                "fulfillment_status": item.fulfillment_status
            } for item in line_items],
            created_at=order.created_at,
            updated_at=order.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting order {order_id} for {shop_domain}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get order"
        )


# ============================================================================
# CUSTOMERS ENDPOINTS
# ============================================================================

@router.get(
    "/shops/{shop_domain}/customers",
    response_model=List[ShopifyCustomerResponse],
    summary="Get customers",
    description="Get customers for a shop with filtering and pagination"
)
async def get_customers(
    shop_domain: str,
    skip: int = Query(0, ge=0, description="Number of customers to skip"),
    limit: int = Query(50, ge=1, le=100, description="Number of customers to return"),
    search: Optional[str] = Query(None, description="Search in name and email"),
    state: Optional[str] = Query(None, description="Filter by state"),
    accepts_marketing: Optional[bool] = Query(None, description="Filter by marketing acceptance"),
    db: Session = Depends(get_db)
):
    """Get customers with filtering."""
    try:
        query = db.query(ShopifyCustomer).filter(
            and_(
                ShopifyCustomer.shop_domain == shop_domain,
                ShopifyCustomer.is_active == True
            )
        )
        
        # Apply filters
        if search:
            query = query.filter(
                or_(
                    ShopifyCustomer.email.ilike(f"%{search}%"),
                    ShopifyCustomer.first_name.ilike(f"%{search}%"),
                    ShopifyCustomer.last_name.ilike(f"%{search}%")
                )
            )
        
        if state:
            query = query.filter(ShopifyCustomer.state == state.lower())
        
        if accepts_marketing is not None:
            query = query.filter(ShopifyCustomer.accepts_marketing == accepts_marketing)
        
        # Apply pagination and ordering
        customers = query.order_by(desc(ShopifyCustomer.updated_at)).offset(skip).limit(limit).all()
        
        # Convert to response format
        response_customers = []
        for customer in customers:
            response_customers.append(ShopifyCustomerResponse(
                id=customer.id,
                shopify_customer_id=customer.shopify_customer_id,
                email=customer.email,
                first_name=customer.first_name,
                last_name=customer.last_name,
                orders_count=customer.orders_count,
                total_spent=customer.total_spent,
                created_at=customer.created_at,
                updated_at=customer.updated_at
            ))
        
        return response_customers
        
    except Exception as e:
        logger.error(f"Error getting customers for {shop_domain}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get customers"
        )


# ============================================================================
# ANALYTICS ENDPOINTS
# ============================================================================

@router.get(
    "/shops/{shop_domain}/analytics/summary",
    summary="Get shop analytics summary",
    description="Get key metrics and analytics for the shop"
)
async def get_analytics_summary(
    shop_domain: str,
    days_back: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db)
):
    """Get analytics summary for the shop."""
    try:
        start_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Total products
        total_products = db.query(func.count(ShopifyProduct.id)).filter(
            and_(
                ShopifyProduct.shop_domain == shop_domain,
                ShopifyProduct.is_active == True
            )
        ).scalar() or 0
        
        # Active products (published)
        active_products = db.query(func.count(ShopifyProduct.id)).filter(
            and_(
                ShopifyProduct.shop_domain == shop_domain,
                ShopifyProduct.status == 'active',
                ShopifyProduct.is_active == True
            )
        ).scalar() or 0
        
        # Total customers
        total_customers = db.query(func.count(ShopifyCustomer.id)).filter(
            and_(
                ShopifyCustomer.shop_domain == shop_domain,
                ShopifyCustomer.is_active == True
            )
        ).scalar() or 0
        
        # Recent orders
        recent_orders = db.query(func.count(ShopifyOrder.id)).filter(
            and_(
                ShopifyOrder.shop_domain == shop_domain,
                ShopifyOrder.created_at_shopify >= start_date
            )
        ).scalar() or 0
        
        # Recent revenue
        recent_revenue = db.query(func.sum(ShopifyOrder.total_price)).filter(
            and_(
                ShopifyOrder.shop_domain == shop_domain,
                ShopifyOrder.created_at_shopify >= start_date,
                ShopifyOrder.financial_status.in_(['paid', 'partially_paid'])
            )
        ).scalar() or 0
        
        # Average order value
        avg_order_value = db.query(func.avg(ShopifyOrder.total_price)).filter(
            and_(
                ShopifyOrder.shop_domain == shop_domain,
                ShopifyOrder.created_at_shopify >= start_date
            )
        ).scalar() or 0
        
        # Top selling products
        top_products = db.query(
            ShopifyProduct.title,
            func.sum(ShopifyOrderLineItem.quantity).label('total_sold')
        ).join(
           ShopifyOrderLineItem, ShopifyProduct.id == ShopifyOrderLineItem.product_id
       ).join(
           ShopifyOrder, ShopifyOrderLineItem.order_id == ShopifyOrder.id
       ).filter(
           and_(
               ShopifyProduct.shop_domain == shop_domain,
               ShopifyOrder.created_at_shopify >= start_date
           )
       ).group_by(
           ShopifyProduct.id, ShopifyProduct.title
       ).order_by(
           desc('total_sold')
       ).limit(10).all()
       
       # Order statuses breakdown
        order_statuses = db.query(
           ShopifyOrder.financial_status,
           func.count(ShopifyOrder.id).label('count')
       ).filter(
           and_(
               ShopifyOrder.shop_domain == shop_domain,
               ShopifyOrder.created_at_shopify >= start_date
           )
       ).group_by(ShopifyOrder.financial_status).all()
       
        return {
           "summary": {
               "total_products": total_products,
               "active_products": active_products,
               "total_customers": total_customers,
               "recent_orders": recent_orders,
               "recent_revenue": float(recent_revenue),
               "average_order_value": float(avg_order_value)
           },
           "top_products": [
               {
                   "title": product.title,
                   "total_sold": product.total_sold
               } for product in top_products
           ],
           "order_statuses": [
               {
                   "status": status.financial_status,
                   "count": status.count
               } for status in order_statuses
           ],
           "period": {
               "days_back": days_back,
               "start_date": start_date.isoformat(),
               "end_date": datetime.utcnow().isoformat()
           }
       }
       
    except Exception as e:
       logger.error(f"Error getting analytics for {shop_domain}: {str(e)}")
       raise HTTPException(
           status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
           detail="Failed to get analytics summary"
       )


# ============================================================================
# SEARCH ENDPOINT FOR CHATBOT
# ============================================================================

@router.get(
   "/shops/{shop_domain}/search",
   summary="Search across all data",
   description="Universal search endpoint for chatbot to find products, orders, customers"
)
async def universal_search(
   shop_domain: str,
   query: str = Query(..., description="Search query"),
   search_type: Optional[str] = Query(None, description="Limit search to: products, orders, customers"),
   limit: int = Query(20, ge=1, le=100, description="Maximum results to return"),
   db: Session = Depends(get_db)
):
   """Universal search endpoint for chatbot."""
   try:
       results = {
           "query": query,
           "products": [],
           "orders": [],
           "customers": [],
           "total_results": 0
       }
       
       # Search products
       if not search_type or search_type == "products":
           products = db.query(ShopifyProduct).filter(
               and_(
                   ShopifyProduct.shop_domain == shop_domain,
                   ShopifyProduct.is_active == True,
                   or_(
                       ShopifyProduct.title.ilike(f"%{query}%"),
                       ShopifyProduct.description.ilike(f"%{query}%"),
                       ShopifyProduct.vendor.ilike(f"%{query}%"),
                       ShopifyProduct.product_type.ilike(f"%{query}%")
                   )
               )
           ).limit(limit // 3 if not search_type else limit).all()
           
           for product in products:
               results["products"].append({
                   "id": product.id,
                   "shopify_product_id": product.shopify_product_id,
                   "title": product.title,
                   "description": product.description[:200] if product.description else "",
                   "handle": product.handle,
                   "vendor": product.vendor,
                   "status": product.status,
                   "type": "product"
               })
       
       # Search orders
       if not search_type or search_type == "orders":
           orders = db.query(ShopifyOrder).filter(
               and_(
                   ShopifyOrder.shop_domain == shop_domain,
                   or_(
                       ShopifyOrder.name.ilike(f"%{query}%"),
                       ShopifyOrder.email.ilike(f"%{query}%"),
                       ShopifyOrder.order_number.ilike(f"%{query}%")
                   )
               )
           ).limit(limit // 3 if not search_type else limit).all()
           
           for order in orders:
               results["orders"].append({
                   "id": order.id,
                   "shopify_order_id": order.shopify_order_id,
                   "name": order.name,
                   "order_number": order.order_number,
                   "email": order.email,
                   "total_price": float(order.total_price) if order.total_price else 0,
                   "financial_status": order.financial_status,
                   "fulfillment_status": order.fulfillment_status,
                   "created_at": order.created_at_shopify.isoformat() if order.created_at_shopify else None,
                   "type": "order"
               })
       
       # Search customers
       if not search_type or search_type == "customers":
           customers = db.query(ShopifyCustomer).filter(
               and_(
                   ShopifyCustomer.shop_domain == shop_domain,
                   ShopifyCustomer.is_active == True,
                   or_(
                       ShopifyCustomer.email.ilike(f"%{query}%"),
                       ShopifyCustomer.first_name.ilike(f"%{query}%"),
                       ShopifyCustomer.last_name.ilike(f"%{query}%")
                   )
               )
           ).limit(limit // 3 if not search_type else limit).all()
           
           for customer in customers:
               results["customers"].append({
                   "id": customer.id,
                   "shopify_customer_id": customer.shopify_customer_id,
                   "email": customer.email,
                   "first_name": customer.first_name,
                   "last_name": customer.last_name,
                   "orders_count": customer.orders_count,
                   "total_spent": float(customer.total_spent) if customer.total_spent else 0,
                   "type": "customer"
               })
       
       results["total_results"] = len(results["products"]) + len(results["orders"]) + len(results["customers"])
       
       return results
       
   except Exception as e:
       logger.error(f"Error in universal search for {shop_domain}: {str(e)}")
       raise HTTPException(
           status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
           detail="Search failed"
       )