import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()

def get_supabase_client() -> Client:
    """Initialize and return a Supabase client."""
    url: str = os.environ.get("SUPABASE_URL")
    key: str = os.environ.get("SUPABASE_KEY")
    
    if not url or not key:
        raise ValueError("Missing SUPABASE_URL or SUPABASE_KEY environment variables.")
        
    return create_client(url, key)

def store_snapshots(supabase: Client, balances: list):
    """Store batch snapshots to the database."""
    if not balances:
        return
    
    try:
        # Supabase generic upsert
        response = supabase.table('wallet_snapshots').insert(balances).execute()
        return response
    except Exception as e:
        print(f"Error storing snapshots: {e}")

def get_unique_tokens(supabase: Client) -> list:
    """Retrieve unique tokens from the latest snapshots."""
    # Simplified approach to get unique tokens requested over last hour
    try:
        from datetime import datetime, timedelta
        one_hour_ago = (datetime.now() - timedelta(hours=1)).isoformat()
        
        # Execute query to get distinct tkns from snp.
        res = supabase.table('wallet_snapshots').select('token_address, chain').gte('captured_at', one_hour_ago).execute()
        
        # Make unique combining address and chain
        unique_tokens = list({ (v['token_address'], v['chain']): v for v in res.data }.values())
        return unique_tokens
    except Exception as e:
        print(f"Error fetching unique tokens: {e}")
        return []

def upsert_token_metadata(supabase: Client, metadata: dict):
    """Upsert to token metadata table."""
    try:
         supabase.table('token_metadata').upsert(metadata, on_conflict="token_address").execute()
    except Exception as e:
        print(f"Error upserting token metadata for {metadata.get('token_address')}: {e}")
