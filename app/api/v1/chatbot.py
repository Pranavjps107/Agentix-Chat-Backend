# app/api/v1/chatbot.py
"""
Chatbot API endpoints for natural language queries.
"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from app.models.database import get_db
from app.services.chatbot_query_service import chat
from app.services.chatbot_query_service import chatbot_query_service
from app.core.logging import logger
from datetime import datetime

router = APIRouter(prefix="/chatbot", tags=["chatbot"])


class ChatbotQuery(BaseModel):
   """Request model for chatbot queries."""
   query: str
   shop_domain: str
   context: dict = {}  # Optional context for conversation


class ChatbotResponse(BaseModel):
   """Response model for chatbot queries."""
   query: str
   intent: str
   response: str
   data: Dict[str, Any]
   suggestions: list = []
   timestamp: str


@router.post(
   "/query",
   response_model=ChatbotResponse,
   summary="Process natural language query",
   description="Process a natural language query and return relevant Shopify data"
)
async def process_chatbot_query(
   request: ChatbotQuery,
   db: Session = Depends(get_db)
):
   """Process a natural language query about Shopify data."""
   try:
       # Process the query
       result = await chatbot_query_service.process_query(
           db, request.shop_domain, request.query
       )
       
       # Generate suggestions based on intent
       suggestions = _generate_suggestions(result.get("intent", "general"))
       
       return ChatbotResponse(
           query=request.query,
           intent=result.get("intent", "general"),
           response=result.get("message", "I found some information for you."),
           data=result.get("data", []),
           suggestions=suggestions,
           timestamp=datetime.utcnow().isoformat()
       )
       
   except Exception as e:
       logger.error(f"Chatbot query error: {str(e)}")
       return ChatbotResponse(
           query=request.query,
           intent="error",
           response="I'm sorry, I encountered an error processing your request. Please try again.",
           data=[],
           suggestions=["Try asking about products", "Search for orders", "Ask for analytics"],
           timestamp=datetime.utcnow().isoformat()
       )


@router.get(
   "/suggestions/{shop_domain}",
   summary="Get query suggestions",
   description="Get suggested queries based on available data"
)
async def get_query_suggestions(
   shop_domain: str,
   db: Session = Depends(get_db)
):
   """Get suggested queries for the chatbot."""
   try:
       # Get some basic stats to generate contextual suggestions
       from app.models.shopify_data import ShopifyProduct, ShopifyOrder, ShopifyCustomer
       from sqlalchemy import func
       
       product_count = db.query(func.count(ShopifyProduct.id)).filter(
           ShopifyProduct.shop_domain == shop_domain
       ).scalar() or 0
       
       order_count = db.query(func.count(ShopifyOrder.id)).filter(
           ShopifyOrder.shop_domain == shop_domain
       ).scalar() or 0
       
       customer_count = db.query(func.count(ShopifyCustomer.id)).filter(
           ShopifyCustomer.shop_domain == shop_domain
       ).scalar() or 0
       
       suggestions = {
           "product_queries": [
               "Show me my best selling products",
               "Which products are out of stock?",
               "Find products with 'shirt' in the title",
               "What are my most expensive products?"
           ],
           "order_queries": [
               "Show me recent orders",
               "Which orders are unfulfilled?",
               "Find orders from last week",
               "Show me pending payments"
           ],
           "customer_queries": [
               "Who are my top customers?",
               "Find customers with high order counts",
               "Show me new customers this month"
           ],
           "analytics_queries": [
               "What's my sales performance this month?",
               "Show me revenue analytics",
               "What's my average order value?"
           ],
           "stats": {
               "products": product_count,
               "orders": order_count,
               "customers": customer_count
           }
       }
       
       return suggestions
       
   except Exception as e:
       logger.error(f"Error getting suggestions for {shop_domain}: {str(e)}")
       raise HTTPException(
           status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
           detail="Failed to get suggestions"
       )


def _generate_suggestions(intent: str) -> list:
   """Generate contextual suggestions based on intent."""
   suggestion_map = {
       "product_search": [
           "Show me out of stock products",
           "Find my best selling products",
           "What are my most expensive items?"
       ],
       "order_search": [
           "Show me unfulfilled orders",
           "Find orders from this week",
           "Which orders need attention?"
       ],
       "customer_search": [
           "Who are my VIP customers?",
           "Show me recent customer signups",
           "Find customers who haven't ordered recently"
       ],
       "analytics": [
           "What's my revenue this month?",
           "Show me sales trends",
           "How many orders did I get today?"
       ],
       "tracking": [
           "Which orders need shipping?",
           "Show me delivery status",
           "Find orders with tracking numbers"
       ],
       "pricing": [
           "Show me pricing analysis",
           "Find products on sale",
           "What's my average product price?"
       ],
       "general": [
           "Show me today's sales",
           "Find my popular products",
           "Which orders need attention?",
           "Show me customer analytics"
       ]
   }
   
   return suggestion_map.get(intent, suggestion_map["general"])