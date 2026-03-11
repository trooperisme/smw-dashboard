import os
from supabase import create_client

def refresh_materialized_views():
    """Trigger the RPC function or execute raw SQL to refresh the aggregated view."""
    
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    supabase = create_client(url, key)
    
    try:
         # Supabase client doesn't support raw SQL from python directly well.
         # So we call a stored RPC function that we will define in Supabase.
         supabase.rpc('refresh_aggregated_holdings').execute()
         print("Materialized views refreshed.")
    except Exception as e:
         print(f"Error refreshing views: {e}")

if __name__ == "__main__":
    refresh_materialized_views()
