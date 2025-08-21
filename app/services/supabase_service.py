"""
Supabase service for additional database operations and real-time features.
"""
from typing import Optional, Dict, Any, List
from supabase import create_client, Client
from app.core.config import settings
from app.core.logging import logger


class SupabaseService:
    """Service class for Supabase-specific operations."""
    
    def __init__(self):
        self.supabase: Client = create_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_KEY
        )
    
    async def get_table_info(self, table_name: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a specific table.
        
        Args:
            table_name: Name of the table
            
        Returns:
            Table information or None if error
        """
        try:
            response = self.supabase.table(table_name).select("*").limit(1).execute()
            return {
                "table_name": table_name,
                "columns": list(response.data[0].keys()) if response.data else [],
                "row_count": len(response.data)
            }
        except Exception as e:
            logger.error(f"Failed to get table info for {table_name}: {str(e)}")
            return None
    
    async def check_connection(self) -> bool:
        """
        Check Supabase connection health.
        
        Returns:
            True if connection is healthy
        """
        try:
            # Simple query to test connection
            response = self.supabase.table("shopify_auth").select("count").execute()
            return True
        except Exception as e:
            logger.error(f"Supabase connection check failed: {str(e)}")
            return False
    
    def setup_realtime_listener(self, table_name: str, callback):
        """
        Set up real-time listener for a table.
        
        Args:
            table_name: Name of the table to listen to
            callback: Function to call when changes occur
        """
        try:
            self.supabase.postgrest.realtime.listen(
                table_name,
                callback
            )
            logger.info(f"Real-time listener set up for table: {table_name}")
        except Exception as e:
            logger.error(f"Failed to set up real-time listener: {str(e)}")


# Global service instance
supabase_service = SupabaseService()