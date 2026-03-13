import asyncio
import aiohttp
from datetime import datetime
import os
from utils.database import get_supabase_client, store_snapshots
from utils.wallet_loader import load_wallets_from_csv

ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

# Hardcoded decimals prevent mis-valuation when Alchemy API returns None
KNOWN_DECIMALS = {
    # Ethereum
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": 6,  # USDC
    "0xdac17f958d2ee523a2206206994597c13d831ec7": 6,  # USDT
    "0x6b175474e89094c44da98b954eedeac495271d0f": 18, # DAI
    # Base
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": 6,  # USDC on Base
    "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2": 6,  # USDT on Base
    # BSC
    "0x55d398326f99059ff775485246999027b3197955": 18, # USDT on BSC
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": 18, # USDC on BSC
}

class BalanceFetcher:
    def __init__(self):
        self.metadata_cache = {}

    async def get_evm_token_decimals(self, session, url, token_address):
        """Fetch token decimals — check known list first, then Alchemy API."""
        # Check hardcoded known decimals first
        lower_addr = token_address.lower() if token_address else None
        for known_addr, decimals in KNOWN_DECIMALS.items():
            if lower_addr == known_addr.lower():
                return decimals
        
        if token_address in self.metadata_cache:
            return self.metadata_cache[token_address]
            
        payload = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "alchemy_getTokenMetadata",
            "params": [token_address]
        }
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    decimals = data.get('result', {}).get('decimals') or 18
                    self.metadata_cache[token_address] = decimals
                    return decimals
        except Exception as e:
            print(f"Error fetching metadata for {token_address}: {e}")
        return 18

    async def fetch_native_eth_balance(self, session, url, wallet_address: str, chain: str) -> dict | None:
        """Fetch native ETH/gas token balance via eth_getBalance."""
        payload = {
            "id": 1,
            "jsonrpc": "2.0",
            "method": "eth_getBalance",
            "params": [wallet_address, "latest"]
        }
        try:
            async with session.post(url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    balance_hex = data.get('result', '0x0')
                    balance_raw = int(balance_hex, 16)
                    if balance_raw == 0:
                        return None
                    return {
                        'token_address': f'ETH_NATIVE_{chain.upper()}',
                        'balance_raw': balance_raw,
                        'decimals': 18,
                        'chain': chain
                    }
        except Exception as e:
            print(f"Error fetching native ETH for {wallet_address} on {chain}: {e}")
        return None

    async def fetch_evm_balances(self, wallet_address: str, chain: str) -> list:
        """Fetch ERC-20 balances for Ethereum, Base, or BSC."""
        
        if chain in ['ethereum', 'base']:
            url = f"https://{chain}-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}"
            payload = {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "alchemy_getTokenBalances",
                "params": [wallet_address]
            }
        elif chain == 'bsc':
            # Note: Standard Ankr RPC requires 'eth_call' against known contracts.
            # To get *all* tokens, Ankr Advanced API 'ankr_getAccountBalance' is needed.
            url = "https://rpc.ankr.com/multichain" 
            payload = {
                "id": 1,
                "jsonrpc": "2.0",
                "method": "ankr_getAccountBalance",
                "params": {"blockchain": "bsc", "walletAddress": wallet_address}
            }
        else:
            return []
            
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tokens = await self.parse_evm_response(session, url, data, chain, wallet_address)
                        # Also fetch native ETH/gas token
                        native = await self.fetch_native_eth_balance(session, url, wallet_address, chain)
                        if native:
                            tokens.append(native)
                        return tokens
            except Exception as e:
                print(f"Error fetching {chain} for {wallet_address}: {e}")
        return []
    
    async def fetch_solana_balances(self, wallet_address: str) -> list:
        """Fetch SPL token balances + native SOL for Solana using Helius."""
        url = f"https://api.helius.xyz/v0/addresses/{wallet_address}/balances?api-key={HELIUS_API_KEY}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        tokens = self.parse_solana_response(data, wallet_address)
                        # Include native SOL balance
                        native_sol_lamports = data.get('nativeBalance', 0)
                        if native_sol_lamports > 0:
                            tokens.append({
                                'token_address': 'SOL_NATIVE',
                                'balance_raw': native_sol_lamports,
                                'decimals': 9,  # SOL has 9 decimals (lamports)
                                'chain': 'solana'
                            })
                        return tokens
            except Exception as e:
                print(f"Error fetching solana for {wallet_address}: {e}")
        return []
    
    async def parse_evm_response(self, session, url, data: dict, chain: str, address: str) -> list:
        """Parse RPC response into standard format."""
        tokens = []
        if chain in ['ethereum', 'base']:
            # Parse Alchemy response
            balances = data.get('result', {}).get('tokenBalances', [])
            for token_data in balances:
                balance_raw = int(token_data.get('tokenBalance', '0'), 16)
                if balance_raw == 0:
                    continue
                
                t_addr = token_data.get('contractAddress')
                decimals = await self.get_evm_token_decimals(session, url, t_addr)
                
                tokens.append({
                    'token_address': t_addr,
                    'balance_raw': balance_raw,
                    'decimals': decimals,
                    'chain': chain
                })
        elif chain == 'bsc':
             # Parse Ankr Advanced response
             assets = data.get('result', {}).get('assets', [])
             for asset in assets:
                 tokens.append({
                    'token_address': asset.get('contractAddress'),
                    'balance_raw': float(asset.get('balance', 0)),
                    'decimals': int(asset.get('tokenDecimals', 18)),
                    'balance_usd': float(asset.get('balanceUsd', 0)),
                    'chain': chain
                 })
        return tokens
    
    def parse_solana_response(self, data: dict, address: str) -> list:
        """Parse Helius response."""
        tokens = []
        for token in data.get('tokens', []):
            tokens.append({
                'token_address': token.get('mint'),
                'balance_raw': token.get('amount'),
                'decimals': int(token.get('decimals', 0)),
                'chain': 'solana'
            })
        return tokens

async def scan_all_wallets():
    """Main loop to scan wallets and push to Supabase."""
    # Ensure config path is relative to script location
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(base_dir, 'data', 'wallets.csv')
    
    wallets = load_wallets_from_csv(csv_path)
    if not wallets:
        print("No wallets loaded. Exiting.")
        return

    fetcher = BalanceFetcher()
    supabase = get_supabase_client()
    
    all_balances = []
    
    for wallet in wallets:
        for chain in wallet['chains']:
            print(f"Fetching {chain} for {wallet['address']}")
            balances = []
            if chain == 'solana':
                balances = await fetcher.fetch_solana_balances(wallet['address'])
            else:
                balances = await fetcher.fetch_evm_balances(wallet['address'], chain)
            
            # Enrich snapshot with core wallet data
            for b in balances:
                b['wallet_address'] = wallet['address']
                b['cluster_id'] = wallet['cluster_id']
                # default to 0 if not set by Ankr
                b['balance_usd'] = b.get('balance_usd', 0) 
            
            all_balances.extend(balances)
            await asyncio.sleep(0.1) # Rate limit protection

    print(f"Storing {len(all_balances)} snapshots to database.")
    store_snapshots(supabase, all_balances)

if __name__ == "__main__":
    asyncio.run(scan_all_wallets())
