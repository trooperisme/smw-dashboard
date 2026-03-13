import asyncio
import aiohttp
from datetime import datetime
from utils.database import get_supabase_client, get_unique_tokens, upsert_token_metadata

# Well-known tokens: bypass Dexscreener lookups entirely for these
# price_usd = None means "fetch live price from CoinGecko"
KNOWN_METADATA = {
    # --- USDC ---
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": {"token_name": "USD Coin", "ticker": "USDC", "price_usd": 1.0, "decimals": 6, "chains": ["ethereum"]},
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": {"token_name": "USD Coin", "ticker": "USDC", "price_usd": 1.0, "decimals": 6, "chains": ["base"]},
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": {"token_name": "USD Coin", "ticker": "USDC", "price_usd": 1.0, "decimals": 18, "chains": ["bsc"]},
    # --- USDT ---
    "0xdac17f958d2ee523a2206206994597c13d831ec7": {"token_name": "Tether USD", "ticker": "USDT", "price_usd": 1.0, "decimals": 6, "chains": ["ethereum"]},
    "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2": {"token_name": "Tether USD", "ticker": "USDT", "price_usd": 1.0, "decimals": 6, "chains": ["base"]},
    "0x55d398326f99059ff775485246999027b3197955": {"token_name": "Tether USD", "ticker": "USDT", "price_usd": 1.0, "decimals": 18, "chains": ["bsc"]},
    # --- Native ETH (tracked as synthetic token) ---
    "eth_native_ethereum": {"token_name": "Ethereum", "ticker": "ETH", "price_usd": None, "decimals": 18, "chains": ["ethereum"]},
    "eth_native_base": {"token_name": "Ethereum", "ticker": "ETH", "price_usd": None, "decimals": 18, "chains": ["base"]},
    # --- Native SOL ---
    "sol_native": {"token_name": "Solana", "ticker": "SOL", "price_usd": None, "decimals": 9, "chains": ["solana"]},
}

# CoinGecko IDs for live price lookup (free API, no key needed)
NATIVE_TOKEN_COINGECKO_IDS = {
    "eth_native_ethereum": "ethereum",
    "eth_native_base": "ethereum",
    "sol_native": "solana",
}

async def fetch_coingecko_prices(token_ids: list) -> dict:
    """Fetch live prices for native tokens from CoinGecko (free, no key)."""
    if not token_ids:
        return {}
    ids_str = ",".join(set(token_ids))
    url = f"https://api.coingecko.com/api/v3/simple/price?ids={ids_str}&vs_currencies=usd"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {k: v.get('usd', 0) for k, v in data.items()}
        except Exception as e:
            print(f"CoinGecko error: {e}")
    return {}

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
                    
                    # LIQUIDITY FLOOR: $1,000 (lowered from $10,000 to catch more real tokens)
                    if liquidity_usd < 1000:
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
    """Main loop to enrich unique tokens seen in recent snapshots."""
    supabase = get_supabase_client()
    tokens = get_unique_tokens(supabase)
    
    if not tokens:
        print("No unique tokens to enrich.")
        return
    
    print(f"Enriching {len(tokens)} tokens.")
    enricher = MarketDataEnricher()
    
    # Pre-fetch live prices for native tokens (ETH, SOL) from CoinGecko
    coingecko_ids_needed = []
    for token in tokens:
        t_addr = token['token_address'].lower()
        if t_addr in NATIVE_TOKEN_COINGECKO_IDS:
            coingecko_ids_needed.append(NATIVE_TOKEN_COINGECKO_IDS[t_addr])
    
    live_prices = await fetch_coingecko_prices(coingecko_ids_needed)
    print(f"Live prices fetched: {live_prices}")
    
    for token in tokens:
        t_addr = token['token_address'].lower()
        chain = token['chain']
        
        # --- FAST PATH: Known tokens bypass Dexscreener ---
        if t_addr in KNOWN_METADATA:
            metadata = KNOWN_METADATA[t_addr].copy()
            # Fill live price for native tokens (ETH, SOL)
            if metadata.get('price_usd') is None:
                cg_id = NATIVE_TOKEN_COINGECKO_IDS.get(t_addr)
                metadata['price_usd'] = live_prices.get(cg_id, 0)
            metadata['token_address'] = token['token_address']
            metadata['is_honeypot'] = False
            metadata['buy_tax'] = 0.0
            metadata['sell_tax'] = 0.0
            metadata['trust_score'] = 100
            metadata['last_updated'] = datetime.now().isoformat()
            metadata['market_cap'] = None
            metadata['liquidity_usd'] = None
            upsert_token_metadata(supabase, metadata)
            print(f"[KNOWN] {metadata['ticker']} on {chain} enriched directly.")
            continue
        
        # --- STANDARD PATH: Dexscreener for unknown tokens ---
        market_data = await enricher.enrich_token(token['token_address'], chain)
        if market_data:
            upsert_token_metadata(supabase, market_data)
        # Rate limit protection
        await asyncio.sleep(0.3)

if __name__ == "__main__":
    asyncio.run(enrich_all_tokens())
