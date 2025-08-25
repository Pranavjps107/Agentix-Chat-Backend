# app/services/chatbot_query_service.py
"""
Specialized service for handling chatbot queries about Shopify data.
"""
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc, func, text
from app.models.shopify_data import (
    ShopifyProduct, ShopifyProductVariant, ShopifyOrder, 
    ShopifyOrderLineItem, ShopifyCustomer
)
from app.core.logging import logger
from decimal import Decimal
from datetime import datetime, timedelta


class ChatbotQueryService:
    """Service for handling natural language queries about Shopify data."""
    
    def __init__(self):
        self.intent_keywords = {
            "product_search": ["product", "item", "sell", "available", "stock", "inventory"],
            "order_search": ["order", "purchase", "bought", "transaction", "payment"],
            "customer_search": ["customer", "buyer", "user", "client"],
            "pricing": ["price", "cost", "expensive", "cheap", "amount"],
            "tracking": ["track", "shipping", "delivery", "fulfillment", "status"],
            "analytics": ["sales", "revenue", "profit", "performance", "analytics", "stats"]
        }
    
    def detect_intent(self, query: str) -> str:
        """Detect the intent of a natural language query."""
        query_lower = query.lower()
        intent_scores = {}
        
        for intent, keywords in self.intent_keywords.items():
            score = sum(1 for keyword in keywords if keyword in query_lower)
            if score > 0:
                intent_scores[intent] = score
        
        if intent_scores:
            return max(intent_scores, key=intent_scores.get)
        return "general"
    
    async def process_query(self, db: Session, shop_domain: str, query: str) -> Dict[str, Any]:
        """Process a natural language query and return relevant data."""
        try:
            intent = self.detect_intent(query)
            query_lower = query.lower()
            
            logger.info(f"Processing query: '{query}' with intent: {intent}")
            
            if intent == "product_search":
                return await self._handle_product_query(db, shop_domain, query_lower)
            elif intent == "order_search":
                return await self._handle_order_query(db, shop_domain, query_lower)
            elif intent == "customer_search":
                return await self._handle_customer_query(db, shop_domain, query_lower)
            elif intent == "pricing":
                return await self._handle_pricing_query(db, shop_domain, query_lower)
            elif intent == "tracking":
                return await self._handle_tracking_query(db, shop_domain, query_lower)
            elif intent == "analytics":
                return await self._handle_analytics_query(db, shop_domain, query_lower)
            else:
                return await self._handle_general_query(db, shop_domain, query_lower)
                
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            return {
                "intent": "error",
                "message": "I'm sorry, I encountered an error processing your request. Please try again.",
                "data": []
            }
    
    async def _handle_product_query(self, db: Session, shop_domain: str, query: str) -> Dict[str, Any]:
        """Handle product-related queries."""
        # Extract product search terms
        search_terms = self._extract_search_terms(query)
        
        # Check for specific product attributes
        if "out of stock" in query or "no stock" in query:
            products = db.query(ShopifyProduct).join(ShopifyProductVariant).filter(
                and_(
                    ShopifyProduct.shop_domain == shop_domain,
                    ShopifyProduct.is_active == True,
                    ShopifyProductVariant.inventory_quantity == 0
                )
            ).distinct().limit(10).all()
            
            return {
                "intent": "product_search",
                "query_type": "out_of_stock",
                "message": f"Found {len(products)} products that are out of stock:",
                "data": [self._format_product_data(product) for product in products]
            }
        
        elif "best seller" in query or "popular" in query:
            # Get best selling products
            best_sellers = db.query(
                ShopifyProduct,
                func.sum(ShopifyOrderLineItem.quantity).label('total_sold')
            ).join(
                ShopifyOrderLineItem, ShopifyProduct.id == ShopifyOrderLineItem.product_id
            ).filter(
                ShopifyProduct.shop_domain == shop_domain
            ).group_by(
                ShopifyProduct.id
            ).order_by(
                desc('total_sold')
            ).limit(10).all()
            
            return {
                "intent": "product_search",
                "query_type": "best_sellers",
                "message": "Here are your best-selling products:",
                "data": [
                    {
                        **self._format_product_data(item[0]),
                        "total_sold": item[1]
                    } for item in best_sellers
                ]
            }
        
        else:
            # General product search
            query_filter = or_(
                ShopifyProduct.title.ilike(f"%{term}%") for term in search_terms
            ) if search_terms else or_(
                ShopifyProduct.title.ilike(f"%{query}%"),
                ShopifyProduct.description.ilike(f"%{query}%"),
                ShopifyProduct.vendor.ilike(f"%{query}%")
            )
            
            products = db.query(ShopifyProduct).filter(
                and_(
                    ShopifyProduct.shop_domain == shop_domain,
                    ShopifyProduct.is_active == True,
                    query_filter
                )
            ).limit(10).all()
            
            message = f"Found {len(products)} products" + (
                f" matching '{' '.join(search_terms)}'" if search_terms 
                else f" related to your search"
            ) + ":"
            
            return {
                "intent": "product_search",
                "query_type": "general",
                "message": message,
                "data": [self._format_product_data(product) for product in products]
            }
    
    async def _handle_order_query(self, db: Session, shop_domain: str, query: str) -> Dict[str, Any]:
        """Handle order-related queries."""
        # Check for recent orders
        if "recent" in query or "latest" in query:
            orders = db.query(ShopifyOrder).filter(
                ShopifyOrder.shop_domain == shop_domain
            ).order_by(desc(ShopifyOrder.created_at_shopify)).limit(10).all()
            
            return {
                "intent": "order_search",
                "query_type": "recent",
                "message": f"Here are the {len(orders)} most recent orders:",
                "data": [self._format_order_data(order) for order in orders]
            }
        
        # Check for pending orders
        elif "pending" in query or "unpaid" in query:
            orders = db.query(ShopifyOrder).filter(
                and_(
                    ShopifyOrder.shop_domain == shop_domain,
                    ShopifyOrder.financial_status.in_(['pending', 'authorized'])
                )
            ).order_by(desc(ShopifyOrder.created_at_shopify)).limit(10).all()
            
            return {
                "intent": "order_search",
                "query_type": "pending",
                "message": f"Found {len(orders)} pending orders:",
                "data": [self._format_order_data(order) for order in orders]
            }
        
        # Check for unfulfilled orders
        elif "unfulfilled" in query or "not shipped" in query:
            orders = db.query(ShopifyOrder).filter(
                and_(
                    ShopifyOrder.shop_domain == shop_domain,
                    or_(
                        ShopifyOrder.fulfillment_status == 'unfulfilled',
                        ShopifyOrder.fulfillment_status.is_(None)
                    )
                )
            ).order_by(desc(ShopifyOrder.created_at_shopify)).limit(10).all()
            
            return {
                "intent": "order_search",
                "query_type": "unfulfilled",
                "message": f"Found {len(orders)} unfulfilled orders:",
                "data": [self._format_order_data(order) for order in orders]
            }
        
        # Search by order number or customer email
        else:
            search_terms = self._extract_search_terms(query)
            if search_terms:
                orders = db.query(ShopifyOrder).filter(
                    and_(
                        ShopifyOrder.shop_domain == shop_domain,
                        or_(
                            *[or_(
                                ShopifyOrder.name.ilike(f"%{term}%"),
                                ShopifyOrder.email.ilike(f"%{term}%"),
                                ShopifyOrder.order_number.ilike(f"%{term}%")
                            ) for term in search_terms]
                        )
                    )
                ).limit(10).all()
                
                return {
                    "intent": "order_search",
                    "query_type": "search",
                    "message": f"Found {len(orders)} orders matching your search:",
                    "data": [self._format_order_data(order) for order in orders]
                }
        
        return {
            "intent": "order_search",
            "query_type": "general",
            "message": "I can help you find orders. Try asking about recent orders, pending orders, or search by order number.",
            "data": []
        }
    
    async def _handle_customer_query(self, db: Session, shop_domain: str, query: str) -> Dict[str, Any]:
        """Handle customer-related queries."""
        # Check for top customers
        if "top customer" in query or "best customer" in query or "vip" in query:
            customers = db.query(ShopifyCustomer).filter(
                and_(
                    ShopifyCustomer.shop_domain == shop_domain,
                    ShopifyCustomer.is_active == True
                )
            ).order_by(desc(ShopifyCustomer.total_spent)).limit(10).all()
            
            return {
                "intent": "customer_search",
                "query_type": "top_customers",
                "message": "Here are your top customers by total spent:",
                "data": [self._format_customer_data(customer) for customer in customers]
            }
        
        # Search by email or name
        else:
            search_terms = self._extract_search_terms(query)
            if search_terms:
                customers = db.query(ShopifyCustomer).filter(
                    and_(
                        ShopifyCustomer.shop_domain == shop_domain,
                        ShopifyCustomer.is_active == True,
                        or_(
                            *[or_(
                                ShopifyCustomer.email.ilike(f"%{term}%"),
                                ShopifyCustomer.first_name.ilike(f"%{term}%"),
                                ShopifyCustomer.last_name.ilike(f"%{term}%")
                            ) for term in search_terms]
                        )
                    )
                ).limit(10).all()
                
                return {
                    "intent": "customer_search",
                    "query_type": "search",
                    "message": f"Found {len(customers)} customers matching your search:",
                    "data": [self._format_customer_data(customer) for customer in customers]
                }
        
        return {
            "intent": "customer_search",
            "query_type": "general",
            "message": "I can help you find customers. Try searching by name or email, or ask about your top customers.",
            "data": []
        }
    
    async def _handle_pricing_query(self, db: Session, shop_domain: str, query: str) -> Dict[str, Any]:
        """Handle pricing-related queries."""
        if "expensive" in query or "highest price" in query:
            # Get most expensive products
            products = db.query(ShopifyProduct).join(ShopifyProductVariant).filter(
                and_(
                    ShopifyProduct.shop_domain == shop_domain,
                    ShopifyProduct.is_active == True
                )
            ).order_by(desc(ShopifyProductVariant.price)).limit(10).all()
            
            return {
                "intent": "pricing",
                "query_type": "expensive",
                "message": "Here are your most expensive products:",
                "data": [self._format_product_data(product) for product in products]
            }
        
        elif "cheap" in query or "lowest price" in query:
            # Get cheapest products
            products = db.query(ShopifyProduct).join(ShopifyProductVariant).filter(
                and_(
                    ShopifyProduct.shop_domain == shop_domain,
                    ShopifyProduct.is_active == True,
                    ShopifyProductVariant.price > 0
                )
            ).order_by(ShopifyProductVariant.price).limit(10).all()
            
            return {
                "intent": "pricing",
                "query_type": "cheap",
                "message": "Here are your most affordable products:",
                "data": [self._format_product_data(product) for product in products]
            }
        
        return {
            "intent": "pricing",
            "query_type": "general",
            "message": "I can help you with pricing information. Ask about expensive or cheap products.",
            "data": []
        }
    
    async def _handle_tracking_query(self, db: Session, shop_domain: str, query: str) -> Dict[str, Any]:
        """Handle tracking and fulfillment queries."""
        search_terms = self._extract_search_terms(query)
        
        if search_terms:
            # Search for specific order tracking
            orders = db.query(ShopifyOrder).filter(
                and_(
                    ShopifyOrder.shop_domain == shop_domain,
                    or_(
                        *[or_(
                            ShopifyOrder.name.ilike(f"%{term}%"),
                            ShopifyOrder.email.ilike(f"%{term}%")
                        ) for term in search_terms]
                    )
                )
            ).limit(5).all()
            
            tracking_data = []
            for order in orders:
                tracking_info = {
                    **self._format_order_data(order),
                    "tracking_numbers": order.tracking_numbers or [],
                    "tracking_urls": order.tracking_urls or [],
                    "fulfillments": order.fulfillments or []
                }
                tracking_data.append(tracking_info)
            
            return {
                "intent": "tracking",
                "query_type": "specific",
                "message": f"Found tracking information for {len(orders)} orders:",
                "data": tracking_data
            }
        
        # General unfulfilled orders
        orders = db.query(ShopifyOrder).filter(
            and_(
                ShopifyOrder.shop_domain == shop_domain,
                or_(
                    ShopifyOrder.fulfillment_status == 'unfulfilled',
                    ShopifyOrder.fulfillment_status.is_(None)
                )
            )
        ).order_by(desc(ShopifyOrder.created_at_shopify)).limit(10).all()
        
        return {
            "intent": "tracking",
            "query_type": "unfulfilled",
            "message": f"Found {len(orders)} orders awaiting fulfillment:",
            "data": [self._format_order_data(order) for order in orders]
        }
    
    async def _handle_analytics_query(self, db: Session, shop_domain: str, query: str) -> Dict[str, Any]:
        """Handle analytics and stats queries."""
        days_back = 30
        if "today" in query:
            days_back = 1
        elif "week" in query:
            days_back = 7
        elif "month" in query:
            days_back = 30
        elif "year" in query:
            days_back = 365
        
        start_date = datetime.utcnow() - timedelta(days=days_back)
        
        # Get key metrics
        total_orders = db.query(func.count(ShopifyOrder.id)).filter(
            and_(
                ShopifyOrder.shop_domain == shop_domain,
                ShopifyOrder.created_at_shopify >= start_date
            )
        ).scalar() or 0
        
        total_revenue = db.query(func.sum(ShopifyOrder.total_price)).filter(
            and_(
                ShopifyOrder.shop_domain == shop_domain,
                ShopifyOrder.created_at_shopify >= start_date,
                ShopifyOrder.financial_status == 'paid'
            )
        ).scalar() or 0
        
        avg_order_value = db.query(func.avg(ShopifyOrder.total_price)).filter(
            and_(
                ShopifyOrder.shop_domain == shop_domain,
                ShopifyOrder.created_at_shopify >= start_date
            )
        ).scalar() or 0
        
        return {
            "intent": "analytics",
            "query_type": "summary",
            "message": f"Analytics for the last {days_back} days:",
            "data": [{
                "period": f"Last {days_back} days",
                "total_orders": total_orders,
                "total_revenue": float(total_revenue),
                "average_order_value": float(avg_order_value),
                "start_date": start_date.isoformat(),
                "end_date": datetime.utcnow().isoformat()
            }]
        }
    
    async def _handle_general_query(self, db: Session, shop_domain: str, query: str) -> Dict[str, Any]:
        """Handle general queries with universal search."""
        search_terms = self._extract_search_terms(query)
        
        if not search_terms:
            return {
                "intent": "general",
                "message": "I can help you find products, orders, customers, and analytics. What would you like to know?",
                "data": []
            }
        
        # Search across all data types
        results = {
            "products": [],
            "orders": [],
            "customers": []
        }
        
        # Search products
        products = db.query(ShopifyProduct).filter(
            and_(
                ShopifyProduct.shop_domain == shop_domain,
                ShopifyProduct.is_active == True,
                or_(
                    *[or_(
                        ShopifyProduct.title.ilike(f"%{term}%"),
                        ShopifyProduct.description.ilike(f"%{term}%")
                    ) for term in search_terms]
                )
            )
        ).limit(5).all()
        
        results["products"] = [self._format_product_data(product) for product in products]
        
        # Search orders
        orders = db.query(ShopifyOrder).filter(
            and_(
                ShopifyOrder.shop_domain == shop_domain,
                or_(
                    *[or_(
                        ShopifyOrder.email.ilike(f"%{term}%"),
                        ShopifyOrder.name.ilike(f"%{term}%")
                    ) for term in search_terms]
                )
            )
        ).limit(5).all()
        
        results["orders"] = [self._format_order_data(order) for order in orders]
        
        # Search customers
        customers = db.query(ShopifyCustomer).filter(
            and_(
                ShopifyCustomer.shop_domain == shop_domain,
                ShopifyCustomer.is_active == True,
                or_(
                    *[or_(
                        ShopifyCustomer.email.ilike(f"%{term}%"),
                        ShopifyCustomer.first_name.ilike(f"%{term}%"),
                        ShopifyCustomer.last_name.ilike(f"%{term}%")
                    ) for term in search_terms]
                )
            )
        ).limit(5).all()
        
        results["customers"] = [self._format_customer_data(customer) for customer in customers]
        
        total_results = len(results["products"]) + len(results["orders"]) + len(results["customers"])
        
        return {
            "intent": "general",
            "query_type": "universal_search",
            "message": f"Found {total_results} results across your store:",
            "data": results
        }
    
    def _extract_search_terms(self, query: str) -> List[str]:
        """Extract meaningful search terms from query."""
        # Remove common words
        stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 
            'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
            'before', 'after', 'above', 'below', 'between', 'among', 'is', 'are',
            'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does',
            'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can'
        }
        
        words = query.lower().split()
        return [word for word in words if word not in stop_words and len(word) > 2]
    
    def _format_product_data(self, product: ShopifyProduct) -> Dict[str, Any]:
        """Format product data for chatbot response."""
        return {
            "id": product.id,
            "shopify_product_id": product.shopify_product_id,
            "title": product.title,
            "description": product.description[:200] + "..." if product.description and len(product.description) > 200 else product.description,
            "handle": product.handle,
            "vendor": product.vendor,
            "product_type": product.product_type,
            "status": product.status,
            "images": product.images[:1] if product.images else [],  # First image only
            "created_at": product.created_at_shopify.isoformat() if product.created_at_shopify else None
        }
    
    def _format_order_data(self, order: ShopifyOrder) -> Dict[str, Any]:
        """Format order data for chatbot response."""
        return {
            "id": order.id,
            "shopify_order_id": order.shopify_order_id,
            "name": order.name,
            "order_number": order.order_number,
            "email": order.email,
            "total_price": float(order.total_price) if order.total_price else 0,
            "currency": order.currency,
            "financial_status": order.financial_status,
            "fulfillment_status": order.fulfillment_status,
            "created_at": order.created_at_shopify.isoformat() if order.created_at_shopify else None
        }
    
    def _format_customer_data(self, customer: ShopifyCustomer) -> Dict[str, Any]:
        """Format customer data for chatbot response."""
        return {
            "id": customer.id,
            "shopify_customer_id": customer.shopify_customer_id,
            "email": customer.email,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "orders_count": customer.orders_count,
            "total_spent": float(customer.total_spent) if customer.total_spent else 0,
            "created_at": customer.created_at_shopify.isoformat() if customer.created_at_shopify else None
        }


# Global service instance
chatbot_query_service = ChatbotQueryService()