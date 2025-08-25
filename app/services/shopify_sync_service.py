# app/services/shopify_sync_service.py
"""
Service for synchronizing Shopify data with local database.
"""
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from app.core.logging import logger
from app.models.database import get_db
from app.models.auth import ShopifyAuth
from app.models.shopify_data import (
    ShopifyShop, ShopifyProduct, ShopifyProductVariant,
    ShopifyCustomer, ShopifyOrder, ShopifyOrderLineItem,
    ShopifySyncLog
)
from app.services.shopify_api_service import shopify_api_service
from app.services.auth_service import shopify_auth_service
from decimal import Decimal


class ShopifySyncService:
    """Service for synchronizing Shopify data."""
    
    def __init__(self):
        self.batch_size = 50
        self.max_retries = 3
        self.retry_delay = 5  # seconds
    
    def create_sync_log(
        self, 
        db: Session, 
        shop_domain: str, 
        sync_type: str
    ) -> ShopifySyncLog:
        """Create a new sync log entry."""
        sync_log = ShopifySyncLog(
            shop_domain=shop_domain,
            sync_type=sync_type,
            status="in_progress",
            start_time=datetime.utcnow()
        )
        db.add(sync_log)
        db.commit()
        db.refresh(sync_log)
        return sync_log
    
    def update_sync_log(
        self,
        db: Session,
        sync_log: ShopifySyncLog,
        status: str,
        **kwargs
    ):
        """Update sync log with results."""
        sync_log.status = status
        sync_log.end_time = datetime.utcnow()
        
        if sync_log.start_time:
            duration = sync_log.end_time - sync_log.start_time
            sync_log.duration_seconds = int(duration.total_seconds())
        
        for key, value in kwargs.items():
            if hasattr(sync_log, key):
                setattr(sync_log, key, value)
        
        db.commit()
        db.refresh(sync_log)
    
    async def sync_shop_info(self, db: Session, shop_domain: str) -> bool:
        """Sync shop information."""
        try:
            # Get access token
            auth_data = shopify_auth_service.get_auth_data(db, shop_domain)
            if not auth_data:
                logger.error(f"No auth data found for shop: {shop_domain}")
                return False
            
            # Fetch shop info from Shopify
            shop_data = await shopify_api_service.get_shop_info(
                shop_domain, auth_data.access_token
            )
            
            if not shop_data:
                logger.error(f"No shop data received for: {shop_domain}")
                return False
            
            # Update or create shop record
            shop = db.query(ShopifyShop).filter(
                ShopifyShop.shop_domain == shop_domain
            ).first()
            
            if shop:
                # Update existing
                shop.name = shop_data.get("name")
                shop.email = shop_data.get("email")
                shop.domain = shop_data.get("primaryDomain", {}).get("host")
                shop.currency = shop_data.get("currencyCode")
                shop.timezone = shop_data.get("ianaTimezone")
                shop.country = shop_data.get("country")
                shop.phone = shop_data.get("phone")
                shop.address = {
                   "address1": shop_data.get("address1"),
                   "address2": shop_data.get("address2"),
                   "city": shop_data.get("city"),
                   "province": shop_data.get("province"),
                   "zip": shop_data.get("zip"),
                   "country": shop_data.get("country")
               }
                shop.plan_name = shop_data.get("plan", {}).get("displayName")
                shop.shop_data = shop_data
                shop.last_synced = datetime.utcnow()
                shop.updated_at = datetime.utcnow()
            else:
               # Create new
               shop = ShopifyShop(
                   shop_domain=shop_domain,
                   shopify_shop_id=shop_data.get("id", "").replace("gid://shopify/Shop/", ""),
                   name=shop_data.get("name"),
                   email=shop_data.get("email"),
                   domain=shop_data.get("primaryDomain", {}).get("host"),
                   currency=shop_data.get("currencyCode"),
                   timezone=shop_data.get("ianaTimezone"),
                   country=shop_data.get("country"),
                   phone=shop_data.get("phone"),
                   address={
                       "address1": shop_data.get("address1"),
                       "address2": shop_data.get("address2"),
                       "city": shop_data.get("city"),
                       "province": shop_data.get("province"),
                       "zip": shop_data.get("zip"),
                       "country": shop_data.get("country")
                   },
                   plan_name=shop_data.get("plan", {}).get("displayName"),
                   shop_data=shop_data,
                   last_synced=datetime.utcnow()
               )
               db.add(shop)
           
            db.commit()
            logger.info(f"Successfully synced shop info for: {shop_domain}")
            return True
           
        except Exception as e:
           logger.error(f"Error syncing shop info for {shop_domain}: {str(e)}")
           return False
   
    async def sync_products(self, db: Session, shop_domain: str) -> Dict[str, int]:
       """Sync all products and variants."""
       sync_log = self.create_sync_log(db, shop_domain, "products")
       stats = {"processed": 0, "created": 0, "updated": 0, "failed": 0}
       
       try:
           # Get access token
           auth_data = shopify_auth_service.get_auth_data(db, shop_domain)
           if not auth_data:
               raise Exception("No auth data found")
           
           cursor = None
           has_next_page = True
           
           while has_next_page:
               # Fetch products from Shopify
               products_data = await shopify_api_service.get_products(
                   shop_domain, auth_data.access_token, self.batch_size, cursor
               )
               
               if not products_data or not products_data.get("edges"):
                   break
               
               # Process each product
               for edge in products_data["edges"]:
                   try:
                       product_node = edge["node"]
                       await self._sync_single_product(db, shop_domain, product_node)
                       stats["processed"] += 1
                       
                       # Check if it's a new or updated product
                       existing_product = db.query(ShopifyProduct).filter(
                           and_(
                               ShopifyProduct.shop_domain == shop_domain,
                               ShopifyProduct.shopify_product_id == product_node["id"].replace("gid://shopify/Product/", "")
                           )
                       ).first()
                       
                       if existing_product and existing_product.created_at < existing_product.updated_at:
                           stats["updated"] += 1
                       else:
                           stats["created"] += 1
                           
                   except Exception as e:
                       logger.error(f"Error syncing product {product_node.get('id', 'unknown')}: {str(e)}")
                       stats["failed"] += 1
               
               # Check for next page
               page_info = products_data.get("pageInfo", {})
               has_next_page = page_info.get("hasNextPage", False)
               cursor = page_info.get("endCursor") if has_next_page else None
               
               # Update sync log with progress
               self.update_sync_log(
                   db, sync_log, "in_progress",
                   records_processed=stats["processed"],
                   last_cursor=cursor
               )
           
           # Update sync log with final results
           self.update_sync_log(
               db, sync_log, "success",
               records_processed=stats["processed"],
               records_created=stats["created"],
               records_updated=stats["updated"],
               records_failed=stats["failed"]
           )
           
           logger.info(f"Products sync completed for {shop_domain}: {stats}")
           return stats
           
       except Exception as e:
           logger.error(f"Products sync failed for {shop_domain}: {str(e)}")
           self.update_sync_log(
               db, sync_log, "error",
               error_message=str(e),
               records_processed=stats["processed"],
               records_failed=stats["failed"]
           )
           return stats
   
    async def _sync_single_product(self, db: Session, shop_domain: str, product_data: Dict[str, Any]):
       """Sync a single product with its variants."""
       shopify_product_id = product_data["id"].replace("gid://shopify/Product/", "")
       
       # Find or create product
       product = db.query(ShopifyProduct).filter(
           and_(
               ShopifyProduct.shop_domain == shop_domain,
               ShopifyProduct.shopify_product_id == shopify_product_id
           )
       ).first()
       
       # Process images
       images = []
       for image_edge in product_data.get("images", {}).get("edges", []):
           image_node = image_edge["node"]
           images.append({
               "id": image_node["id"],
               "url": image_node["url"],
               "alt_text": image_node.get("altText"),
               "width": image_node.get("width"),
               "height": image_node.get("height")
           })
       
       # Process options
       options = []
       for option in product_data.get("options", []):
           options.append({
               "id": option["id"],
               "name": option["name"],
               "values": option["values"],
               "position": option["position"]
           })
       
       if product:
           # Update existing product
           product.title = product_data["title"]
           product.description = product_data.get("description")
           product.handle = product_data["handle"]
           product.vendor = product_data.get("vendor")
           product.product_type = product_data.get("productType")
           product.status = product_data["status"].lower()
           product.tags = product_data.get("tags", [])
           product.images = images
           product.options = options
           product.seo_title = product_data.get("seo", {}).get("title")
           product.seo_description = product_data.get("seo", {}).get("description")
           product.published_at = self._parse_datetime(product_data.get("publishedAt"))
           product.created_at_shopify = self._parse_datetime(product_data["createdAt"])
           product.updated_at_shopify = self._parse_datetime(product_data["updatedAt"])
           product.last_synced = datetime.utcnow()
           product.updated_at = datetime.utcnow()
       else:
           # Create new product
           product = ShopifyProduct(
               shop_domain=shop_domain,
               shopify_product_id=shopify_product_id,
               title=product_data["title"],
               description=product_data.get("description"),
               handle=product_data["handle"],
               vendor=product_data.get("vendor"),
               product_type=product_data.get("productType"),
               status=product_data["status"].lower(),
               tags=product_data.get("tags", []),
               images=images,
               options=options,
               seo_title=product_data.get("seo", {}).get("title"),
               seo_description=product_data.get("seo", {}).get("description"),
               published_at=self._parse_datetime(product_data.get("publishedAt")),
               created_at_shopify=self._parse_datetime(product_data["createdAt"]),
               updated_at_shopify=self._parse_datetime(product_data["updatedAt"]),
               last_synced=datetime.utcnow()
           )
           db.add(product)
       
       db.commit()
       db.refresh(product)
       
       # Sync variants
       await self._sync_product_variants(db, product, product_data.get("variants", {}).get("edges", []))
   
    async def _sync_product_variants(self, db: Session, product: ShopifyProduct, variants_data: List[Dict[str, Any]]):
       """Sync product variants."""
       for variant_edge in variants_data:
           variant_data = variant_edge["node"]
           shopify_variant_id = variant_data["id"].replace("gid://shopify/ProductVariant/", "")
           
           # Find or create variant
           variant = db.query(ShopifyProductVariant).filter(
               and_(
                   ShopifyProductVariant.product_id == product.id,
                   ShopifyProductVariant.shopify_variant_id == shopify_variant_id
               )
           ).first()
           
           # Process selected options
           options = {f"option{i+1}": None for i in range(3)}
           for option in variant_data.get("selectedOptions", []):
               option_name = option["name"].lower()
               if "size" in option_name or "1" in option_name:
                   options["option1"] = option["value"]
               elif "color" in option_name or "2" in option_name:
                   options["option2"] = option["value"]
               elif "3" in option_name:
                   options["option3"] = option["value"]
           
           if variant:
               # Update existing variant
               variant.title = variant_data["title"]
               variant.price = Decimal(str(variant_data["price"]))
               variant.compare_at_price = Decimal(str(variant_data["compareAtPrice"])) if variant_data.get("compareAtPrice") else None
               variant.sku = variant_data.get("sku")
               variant.barcode = variant_data.get("barcode")
               variant.inventory_quantity = variant_data.get("inventoryQuantity", 0)
               variant.inventory_policy = variant_data.get("inventoryPolicy")
               variant.inventory_management = variant_data.get("inventoryManagement")
               variant.weight = Decimal(str(variant_data["weight"])) if variant_data.get("weight") else None
               variant.weight_unit = variant_data.get("weightUnit")
               variant.requires_shipping = variant_data.get("requiresShipping", True)
               variant.taxable = variant_data.get("taxable", True)
               variant.option1 = options["option1"]
               variant.option2 = options["option2"]
               variant.option3 = options["option3"]
               variant.image_id = variant_data.get("image", {}).get("id")
               variant.available = variant_data.get("availableForSale", True)
               variant.last_synced = datetime.utcnow()
               variant.updated_at = datetime.utcnow()
           else:
               # Create new variant
               variant = ShopifyProductVariant(
                   product_id=product.id,
                   shop_domain=product.shop_domain,
                   shopify_variant_id=shopify_variant_id,
                   shopify_product_id=product.shopify_product_id,
                   title=variant_data["title"],
                   price=Decimal(str(variant_data["price"])),
                   compare_at_price=Decimal(str(variant_data["compareAtPrice"])) if variant_data.get("compareAtPrice") else None,
                   sku=variant_data.get("sku"),
                   barcode=variant_data.get("barcode"),
                   inventory_quantity=variant_data.get("inventoryQuantity", 0),
                   inventory_policy=variant_data.get("inventoryPolicy"),
                   inventory_management=variant_data.get("inventoryManagement"),
                   weight=Decimal(str(variant_data["weight"])) if variant_data.get("weight") else None,
                   weight_unit=variant_data.get("weightUnit"),
                   requires_shipping=variant_data.get("requiresShipping", True),
                   taxable=variant_data.get("taxable", True),
                   option1=options["option1"],
                   option2=options["option2"],
                   option3=options["option3"],
                   image_id=variant_data.get("image", {}).get("id"),
                   available=variant_data.get("availableForSale", True),
                   last_synced=datetime.utcnow()
               )
               db.add(variant)
       
       db.commit()
   
    async def sync_orders(self, db: Session, shop_domain: str, days_back: int = 30) -> Dict[str, int]:
       """Sync orders from the last N days."""
       sync_log = self.create_sync_log(db, shop_domain, "orders")
       stats = {"processed": 0, "created": 0, "updated": 0, "failed": 0}
       
       try:
           # Get access token
           auth_data = shopify_auth_service.get_auth_data(db, shop_domain)
           if not auth_data:
               raise Exception("No auth data found")
           
           # Build query filter for recent orders
           since_date = (datetime.utcnow() - timedelta(days=days_back)).isoformat()
           query_filter = f"created_at:>={since_date}"
           
           cursor = None
           has_next_page = True
           
           while has_next_page:
               # Fetch orders from Shopify
               orders_data = await shopify_api_service.get_orders(
                   shop_domain, auth_data.access_token, self.batch_size, cursor, query_filter
               )
               
               if not orders_data or not orders_data.get("edges"):
                   break
               
               # Process each order
               for edge in orders_data["edges"]:
                   try:
                       order_node = edge["node"]
                       await self._sync_single_order(db, shop_domain, order_node)
                       stats["processed"] += 1
                       
                       # Check if it's a new or updated order
                       existing_order = db.query(ShopifyOrder).filter(
                           and_(
                               ShopifyOrder.shop_domain == shop_domain,
                               ShopifyOrder.shopify_order_id == order_node["id"].replace("gid://shopify/Order/", "")
                           )
                       ).first()
                       
                       if existing_order and existing_order.created_at < existing_order.updated_at:
                           stats["updated"] += 1
                       else:
                           stats["created"] += 1
                           
                   except Exception as e:
                       logger.error(f"Error syncing order {order_node.get('id', 'unknown')}: {str(e)}")
                       stats["failed"] += 1
               
               # Check for next page
               page_info = orders_data.get("pageInfo", {})
               has_next_page = page_info.get("hasNextPage", False)
               cursor = page_info.get("endCursor") if has_next_page else None
               
               # Update sync log with progress
               self.update_sync_log(
                   db, sync_log, "in_progress",
                   records_processed=stats["processed"],
                   last_cursor=cursor
               )
           
           # Update sync log with final results
           self.update_sync_log(
               db, sync_log, "success",
               records_processed=stats["processed"],
               records_created=stats["created"],
               records_updated=stats["updated"],
               records_failed=stats["failed"]
           )
           
           logger.info(f"Orders sync completed for {shop_domain}: {stats}")
           return stats
           
       except Exception as e:
           logger.error(f"Orders sync failed for {shop_domain}: {str(e)}")
           self.update_sync_log(
               db, sync_log, "error",
               error_message=str(e),
               records_processed=stats["processed"],
               records_failed=stats["failed"]
           )
           return stats
   
    async def _sync_single_order(self, db: Session, shop_domain: str, order_data: Dict[str, Any]):
       """Sync a single order with its line items."""
       shopify_order_id = order_data["id"].replace("gid://shopify/Order/", "")
       
       # Find or create customer if exists
       customer_id = None
       if order_data.get("customer"):
           customer_id = await self._sync_order_customer(db, shop_domain, order_data["customer"])
       
       # Find or create order
       order = db.query(ShopifyOrder).filter(
           and_(
               ShopifyOrder.shop_domain == shop_domain,
               ShopifyOrder.shopify_order_id == shopify_order_id
           )
       ).first()
       
       # Extract financial amounts
       total_price_data = order_data.get("totalPriceSet", {}).get("shopMoney", {})
       subtotal_price_data = order_data.get("subtotalPriceSet", {}).get("shopMoney", {})
       total_tax_data = order_data.get("totalTaxSet", {}).get("shopMoney", {})
       total_discounts_data = order_data.get("totalDiscountsSet", {}).get("shopMoney", {})
       total_shipping_data = order_data.get("totalShippingPriceSet", {}).get("shopMoney", {})
       
       # Process fulfillments for tracking
       tracking_numbers = []
       tracking_urls = []
       fulfillments = []
       
       for fulfillment in order_data.get("fulfillments", []):
           fulfillments.append({
               "status": fulfillment.get("status"),
               "updated_at": fulfillment.get("updatedAt")
           })
           
           for tracking in fulfillment.get("trackingInfo", []):
               if tracking.get("number"):
                   tracking_numbers.append(tracking["number"])
               if tracking.get("url"):
                   tracking_urls.append(tracking["url"])
       
       if order:
           # Update existing order
           order.customer_id = customer_id
           order.shopify_customer_id = order_data.get("customer", {}).get("id", "").replace("gid://shopify/Customer/", "")
           order.email = order_data.get("email")
           order.phone = order_data.get("phone")
           order.total_price = Decimal(str(total_price_data.get("amount", "0")))
           order.subtotal_price = Decimal(str(subtotal_price_data.get("amount", "0")))
           order.total_tax = Decimal(str(total_tax_data.get("amount", "0")))
           order.total_discounts = Decimal(str(total_discounts_data.get("amount", "0")))
           order.total_shipping = Decimal(str(total_shipping_data.get("amount", "0")))
           order.currency = total_price_data.get("currencyCode", "USD")
           order.financial_status = order_data.get("financialStatus", "").lower()
           order.fulfillment_status = order_data.get("fulfillmentStatus", "").lower()
           order.billing_address = order_data.get("billingAddress")
           order.shipping_address = order_data.get("shippingAddress")
           order.fulfillments = fulfillments
           order.tracking_numbers = tracking_numbers
           order.tracking_urls = tracking_urls
           order.tags = order_data.get("tags", [])
           order.note = order_data.get("note")
           order.created_at_shopify = self._parse_datetime(order_data["createdAt"])
           order.updated_at_shopify = self._parse_datetime(order_data["updatedAt"])
           order.processed_at = self._parse_datetime(order_data.get("processedAt"))
           order.closed_at = self._parse_datetime(order_data.get("closedAt"))
           order.cancelled_at = self._parse_datetime(order_data.get("cancelledAt"))
           order.cancel_reason = order_data.get("cancelReason")
           order.last_synced = datetime.utcnow()
           order.updated_at = datetime.utcnow()
       else:
           # Create new order
           order = ShopifyOrder(
               shop_domain=shop_domain,
               customer_id=customer_id,
               shopify_order_id=shopify_order_id,
               shopify_customer_id=order_data.get("customer", {}).get("id", "").replace("gid://shopify/Customer/", ""),
               order_number=str(order_data.get("orderNumber", "")),
               name=order_data["name"],
               email=order_data.get("email"),
               phone=order_data.get("phone"),
               total_price=Decimal(str(total_price_data.get("amount", "0"))),
               subtotal_price=Decimal(str(subtotal_price_data.get("amount", "0"))),
               total_tax=Decimal(str(total_tax_data.get("amount", "0"))),
               total_discounts=Decimal(str(total_discounts_data.get("amount", "0"))),
               total_shipping=Decimal(str(total_shipping_data.get("amount", "0"))),
               currency=total_price_data.get("currencyCode", "USD"),
               financial_status=order_data.get("financialStatus", "").lower(),
               fulfillment_status=order_data.get("fulfillmentStatus", "").lower(),
               billing_address=order_data.get("billingAddress"),
               shipping_address=order_data.get("shippingAddress"),
               fulfillments=fulfillments,
               tracking_numbers=tracking_numbers,
               tracking_urls=tracking_urls,
               tags=order_data.get("tags", []),
               note=order_data.get("note"),
               created_at_shopify=self._parse_datetime(order_data["createdAt"]),
               updated_at_shopify=self._parse_datetime(order_data["updatedAt"]),
               processed_at=self._parse_datetime(order_data.get("processedAt")),
               closed_at=self._parse_datetime(order_data.get("closedAt")),
               cancelled_at=self._parse_datetime(order_data.get("cancelledAt")),
               cancel_reason=order_data.get("cancelReason"),
               last_synced=datetime.utcnow()
           )
           db.add(order)
       
       db.commit()
       db.refresh(order)
       
       # Sync line items
       await self._sync_order_line_items(db, order, order_data.get("lineItems", {}).get("edges", []))
   
    async def _sync_order_customer(self, db: Session, shop_domain: str, customer_data: Dict[str, Any]) -> Optional[int]:
       """Sync customer from order data."""
       if not customer_data or not customer_data.get("id"):
           return None
       
       shopify_customer_id = customer_data["id"].replace("gid://shopify/Customer/", "")
       
       # Find or create customer
       customer = db.query(ShopifyCustomer).filter(
           and_(
               ShopifyCustomer.shop_domain == shop_domain,
               ShopifyCustomer.shopify_customer_id == shopify_customer_id
           )
       ).first()
       
       if customer:
           # Update existing customer with order data
           customer.first_name = customer_data.get("firstName")
           customer.last_name = customer_data.get("lastName")
           customer.email = customer_data.get("email")
           customer.phone = customer_data.get("phone")
           customer.orders_count = customer_data.get("ordersCount", 0)
           
           total_spent_data = customer_data.get("totalSpentV2", {})
           if total_spent_data.get("amount"):
               customer.total_spent = Decimal(str(total_spent_data["amount"]))
           
           customer.last_synced = datetime.utcnow()
           customer.updated_at = datetime.utcnow()
       else:
           # Create new customer
           total_spent_data = customer_data.get("totalSpentV2", {})
           total_spent = Decimal(str(total_spent_data.get("amount", "0")))
           
           customer = ShopifyCustomer(
               shop_domain=shop_domain,
               shopify_customer_id=shopify_customer_id,
               email=customer_data.get("email"),
               first_name=customer_data.get("firstName"),
               last_name=customer_data.get("lastName"),
               phone=customer_data.get("phone"),
               orders_count=customer_data.get("ordersCount", 0),
               total_spent=total_spent,
               last_synced=datetime.utcnow()
           )
           db.add(customer)
       
       db.commit()
       db.refresh(customer)
       return customer.id
   
    async def _sync_order_line_items(self, db: Session, order: ShopifyOrder, line_items_data: List[Dict[str, Any]]):
       """Sync order line items."""
       # Delete existing line items for this order
       db.query(ShopifyOrderLineItem).filter(
           ShopifyOrderLineItem.order_id == order.id
       ).delete()
       db.commit()
       
       for item_edge in line_items_data:
           item_data = item_edge["node"]
           
           # Find related product
           product_id = None
           if item_data.get("product", {}).get("id"):
               shopify_product_id = item_data["product"]["id"].replace("gid://shopify/Product/", "")
               product = db.query(ShopifyProduct).filter(
                   and_(
                       ShopifyProduct.shop_domain == order.shop_domain,
                       ShopifyProduct.shopify_product_id == shopify_product_id
                   )
               ).first()
               if product:
                   product_id = product.id
           
           # Extract price information
           price_data = item_data.get("originalUnitPriceSet", {}).get("shopMoney", {})
           discount_data = item_data.get("totalDiscountSet", {}).get("shopMoney", {})
           
           line_item = ShopifyOrderLineItem(
               order_id=order.id,
               product_id=product_id,
               shop_domain=order.shop_domain,
               shopify_line_item_id=item_data["id"].replace("gid://shopify/LineItem/", ""),
               shopify_order_id=order.shopify_order_id,
               shopify_product_id=item_data.get("product", {}).get("id", "").replace("gid://shopify/Product/", ""),
               shopify_variant_id=item_data.get("variant", {}).get("id", "").replace("gid://shopify/ProductVariant/", ""),
               title=item_data["title"],
               name=item_data["name"],
               variant_title=item_data.get("variantTitle"),
               sku=item_data.get("sku"),
               vendor=item_data.get("vendor"),
               product_type=item_data.get("productType"),
               quantity=item_data["quantity"],
               price=Decimal(str(price_data.get("amount", "0"))),
               total_discount=Decimal(str(discount_data.get("amount", "0"))),
               fulfillment_service=item_data.get("fulfillmentService", {}).get("serviceName"),
               fulfillment_status=item_data.get("fulfillmentStatus"),
               properties=[attr for attr in item_data.get("customAttributes", [])],
               tax_lines=item_data.get("taxLines", [])
           )
           db.add(line_item)
       
       db.commit()
   
    async def sync_customers(self, db: Session, shop_domain: str) -> Dict[str, int]:
       """Sync all customers."""
       sync_log = self.create_sync_log(db, shop_domain, "customers")
       stats = {"processed": 0, "created": 0, "updated": 0, "failed": 0}
       
       try:
           # Get access token
           auth_data = shopify_auth_service.get_auth_data(db, shop_domain)
           if not auth_data:
               raise Exception("No auth data found")
           
           cursor = None
           has_next_page = True
           
           while has_next_page:
               # Fetch customers from Shopify
               customers_data = await shopify_api_service.get_customers(
                   shop_domain, auth_data.access_token, self.batch_size, cursor
               )
               
               if not customers_data or not customers_data.get("edges"):
                   break
               
               # Process each customer
               for edge in customers_data["edges"]:
                   try:
                       customer_node = edge["node"]
                       await self._sync_single_customer(db, shop_domain, customer_node)
                       stats["processed"] += 1
                       
                       # Check if it's a new or updated customer
                       existing_customer = db.query(ShopifyCustomer).filter(
                           and_(
                               ShopifyCustomer.shop_domain == shop_domain,
                               ShopifyCustomer.shopify_customer_id == customer_node["id"].replace("gid://shopify/Customer/", "")
                           )
                       ).first()
                       
                       if existing_customer and existing_customer.created_at < existing_customer.updated_at:
                           stats["updated"] += 1
                       else:
                           stats["created"] += 1
                           
                   except Exception as e:
                       logger.error(f"Error syncing customer {customer_node.get('id', 'unknown')}: {str(e)}")
                       stats["failed"] += 1
               
               # Check for next page
               page_info = customers_data.get("pageInfo", {})
               has_next_page = page_info.get("hasNextPage", False)
               cursor = page_info.get("endCursor") if has_next_page else None
           
           # Update sync log with final results
           self.update_sync_log(
               db, sync_log, "success",
               records_processed=stats["processed"],
               records_created=stats["created"],
               records_updated=stats["updated"],
               records_failed=stats["failed"]
           )
           
           logger.info(f"Customers sync completed for {shop_domain}: {stats}")
           return stats
           
       except Exception as e:
            logger.error(f"Customers sync failed for {shop_domain}: {str(e)}")
            self.update_sync_log(
               db, sync_log, "error",
               error_message=str(e),
               records_processed=stats["processed"],
               records_failed=stats["failed"]
           )
            return stats
       
    async def _sync_single_customer(self, db: Session, shop_domain: str, customer_data: Dict[str, Any]):
       """Sync a single customer."""
       shopify_customer_id = customer_data["id"].replace("gid://shopify/Customer/", "")
       
       # Find or create customer
       customer = db.query(ShopifyCustomer).filter(
           and_(
               ShopifyCustomer.shop_domain == shop_domain,
               ShopifyCustomer.shopify_customer_id == shopify_customer_id
           )
       ).first()
       
       # Process addresses
       addresses = []
       for address in customer_data.get("addresses", []):
           addresses.append({
               "first_name": address.get("firstName"),
               "last_name": address.get("lastName"),
               "company": address.get("company"),
               "address1": address.get("address1"),
               "address2": address.get("address2"),
               "city": address.get("city"),
               "province": address.get("province"),
               "country": address.get("country"),
               "zip": address.get("zip"),
               "phone": address.get("phone")
           })
       
       total_spent_data = customer_data.get("totalSpentV2", {})
       total_spent = Decimal(str(total_spent_data.get("amount", "0")))
       
       if customer:
           # Update existing customer
           customer.email = customer_data.get("email")
           customer.first_name = customer_data.get("firstName")
           customer.last_name = customer_data.get("lastName")
           customer.phone = customer_data.get("phone")
           customer.accepts_marketing = customer_data.get("acceptsMarketing", False)
           customer.orders_count = customer_data.get("ordersCount", 0)
           customer.total_spent = total_spent
           customer.state = customer_data.get("state", "").lower()
           customer.verified_email = customer_data.get("verifiedEmail", False)
           customer.tax_exempt = customer_data.get("taxExempt", False)
           customer.tags = customer_data.get("tags", [])
           customer.addresses = addresses
           customer.default_address = customer_data.get("defaultAddress")
           customer.created_at_shopify = self._parse_datetime(customer_data["createdAt"])
           customer.updated_at_shopify = self._parse_datetime(customer_data["updatedAt"])
           customer.last_synced = datetime.utcnow()
           customer.updated_at = datetime.utcnow()
       else:
           # Create new customer
           customer = ShopifyCustomer(
               shop_domain=shop_domain,
               shopify_customer_id=shopify_customer_id,
               email=customer_data.get("email"),
               first_name=customer_data.get("firstName"),
               last_name=customer_data.get("lastName"),
               phone=customer_data.get("phone"),
               accepts_marketing=customer_data.get("acceptsMarketing", False),
               orders_count=customer_data.get("ordersCount", 0),
               total_spent=total_spent,
               state=customer_data.get("state", "").lower(),
               verified_email=customer_data.get("verifiedEmail", False),
               tax_exempt=customer_data.get("taxExempt", False),
               tags=customer_data.get("tags", []),
               addresses=addresses,
               default_address=customer_data.get("defaultAddress"),
               created_at_shopify=self._parse_datetime(customer_data["createdAt"]),
               updated_at_shopify=self._parse_datetime(customer_data["updatedAt"]),
               last_synced=datetime.utcnow()
           )
           db.add(customer)
       
       db.commit()
   
    async def full_sync(self, db: Session, shop_domain: str) -> Dict[str, Dict[str, int]]:
       """Perform full synchronization of all data."""
       logger.info(f"Starting full sync for shop: {shop_domain}")
       
       results = {}
       
       try:
           # Sync shop info first
           await self.sync_shop_info(db, shop_domain)
           
           # Sync products and variants
           results["products"] = await self.sync_products(db, shop_domain)
           
           # Sync customers
           results["customers"] = await self.sync_customers(db, shop_domain)
           
           # Sync orders (last 90 days)
           results["orders"] = await self.sync_orders(db, shop_domain, days_back=90)
           
           logger.info(f"Full sync completed for shop: {shop_domain}")
           
       except Exception as e:
           logger.error(f"Full sync failed for {shop_domain}: {str(e)}")
           raise
       
       return results
   
    def _parse_datetime(self, datetime_str: Optional[str]) -> Optional[datetime]:
       """Parse datetime string from Shopify API."""
       if not datetime_str:
           return None
       
       try:
           # Handle ISO format with timezone
           if datetime_str.endswith('Z'):
               return datetime.fromisoformat(datetime_str[:-1])
           elif '+' in datetime_str or datetime_str.count('-') > 2:
               # Handle timezone offsets
               return datetime.fromisoformat(datetime_str.replace('Z', '+00:00'))
           else:
               return datetime.fromisoformat(datetime_str)
       except (ValueError, TypeError):
           logger.warning(f"Could not parse datetime: {datetime_str}")
           return None


# Global service instance
shopify_sync_service = ShopifySyncService()