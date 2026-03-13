import asyncio
import aiohttp
from datetime import datetime
from utils.database import get_supabase_client, get_unique_tokens, upsert_token_metadata

class MarketDataEnricher:
    
    async def check_security(self, token_address: str, chain: str) -> dict:
        """Check token security via GoPlus API."""
        chain_ids = {
            'ethereum': '1',
            'base': '8453',
            'bsc': '56'
        }
        chain_id = chain_ids.get(chain)
        if not chain_id:
            return {'is_honeypot': False, 'buy_tax': 0, 'sell_tax': 0, 'trust_score': 100}
            
        url = f"https://api.gopluslabs.io/api/v1/token_security/{chain_id}?contract_addresses={token_address}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        res = await resp.json()
                        data = res.get('result', {}).get(token_address.lower(), {})
                        
                        return {
                            'is_honeypot': data.get('is_honeypot') == '1',
                            'buy_tax': float(data.get('buy_tax', 0)),
                            'sell_tax': float(data.get('sell_tax', 0)),
                            'trust_score': int(data.get('trust_score', 80)) if data.get('trust_score') else 80
                        }
            except Exception as e:
                print(f"GoPlus Error for {token_address}: {e}")
        return {'is_honeypot': False, 'buy_tax': 0, 'sell_tax': 0, 'trust_score': 50}

    async def enrich_token(self, token_address: str, chain: str) -> dict:
        """Fetch market data from Dexscreener to retrieve Market Cap and Token Age."""
        
        # Format chain name for Dexscreener URL
        chain_map = {
            'ethereum': 'ethereum',
            'base': 'base',
            'bsc': 'bsc',
            'solana': 'solana'
        }
        
        dex_chain = chain_map.get(chain)
        if not dex_chain:
            return None

        url = f"https://api.dexscreener.com/latest/dex/tokens/{token_address}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        return None
                    
                    data = await resp.json()
                    pairs = data.get('pairs', [])
                    if not pairs:
                        return None
                    
                    # Target pair with highest USD liquidity
                    primary_pair = max(pairs, key=lambda p: float(p.get('liquidity', {}).get('usd', 0)))
                    liquidity_usd = float(primary_pair.get('liquidity', {}).get('usd', 0))
                    
                    # LIQUIDITY FLOOR: $10,000
                    if liquidity_usd < 10000:
                        return None
                    
                    pair_created_at = primary_pair.get('pairCreatedAt')
                    created_date = datetime.fromtimestamp(pair_created_at / 1000) if pair_created_at else None
                    
                    # For tokens without marketCap via API, Dexscreener often uses FDV 
                    mc = primary_pair.get('marketCap') or primary_pair.get('fdv')
                    
                    # Fetch Security Data
                    security = await self.check_security(token_address, chain)
                    
                    return {
                        'token_address': token_address,
                        'chains': [chain],
                        'token_name': primary_pair.get('baseToken', {}).get('name'),
                        'ticker': primary_pair.get('baseToken', {}).get('symbol'),
                        'market_cap': mc,
                        'price_usd': float(primary_pair.get('priceUsd', 0) or 0),
                        'decimals': int(primary_pair.get('quoteToken', {}).get('decimals', 18)),
                        'pair_created_at': created_date.isoformat() if created_date else None,
                        'liquidity_usd': liquidity_usd,
                        'is_honeypot': security['is_honeypot'],
                        'buy_tax': security['buy_tax'],
                        'sell_tax': security['sell_tax'],
                        'trust_score': security['trust_score'],
                        'last_updated': datetime.now().isoformat()
                    }
            except Exception as e:
                print(f"Error enriching {token_address} on {chain}: {e}")
        return None

async def enrich_all_tokens():
    """Main loop to enrich unique tokens seen in recent snaphshots."""
    supabase = get_supabase_client()
    tokens = get_unique_tokens(supabase)
    
    if not tokens:
         print("No unique tokens to enrich.")
         return
    
    print(f"Enriching {len(tokens)} tokens.")
    enricher = MarketDataEnricher()
    
    for token in tokens:
         market_data = await enricher.enrich_token(token['token_address'], token['chain'])
         if market_data:
             upsert_token_metadata(supabase, market_data)
         # Rate limit protection (Dexscreener is generous but smart to throttle)
         await asyncio.sleep(0.3)

if __name__ == "__main__":
    asyncio.run(enrich_all_tokens())
