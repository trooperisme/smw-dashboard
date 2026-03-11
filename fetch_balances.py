import asyncio
import aiohttp
from datetime import datetime
import os
from utils.database import get_supabase_client, store_snapshots
from utils.wallet_loader import load_wallets_from_csv

ALCHEMY_API_KEY = os.getenv("ALCHEMY_API_KEY")
HELIUS_API_KEY = os.getenv("HELIUS_API_KEY")

class BalanceFetcher:
    
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
                        return self.parse_evm_response(data, chain, wallet_address)
            except Exception as e:
                print(f"Error fetching {chain} for {wallet_address}: {e}")
        return []
    
    async def fetch_solana_balances(self, wallet_address: str) -> list:
        """Fetch SPL token balances for Solana using Helius."""
        url = f"https://api.helius.xyz/v0/addresses/{wallet_address}/balances?api-key={HELIUS_API_KEY}"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return self.parse_solana_response(data, wallet_address)
            except Exception as e:
                print(f"Error fetching solana for {wallet_address}: {e}")
        return []
    
    def parse_evm_response(self, data: dict, chain: str, address: str) -> list:
        """Parse RPC response into standard format."""
        tokens = []
        if chain in ['ethereum', 'base']:
            # Parse Alchemy response
            balances = data.get('result', {}).get('tokenBalances', [])
            for token_data in balances:
                balance_raw = int(token_data.get('tokenBalance', '0'), 16)
                if balance_raw == 0:
                    continue
                tokens.append({
                    'token_address': token_data.get('contractAddress'),
                    'balance_raw': balance_raw,
                    'chain': chain
                })
        elif chain == 'bsc':
             # Parse Ankr Advanced response
             assets = data.get('result', {}).get('assets', [])
             for asset in assets:
                 tokens.append({
                    'token_address': asset.get('contractAddress'),
                    'balance_raw': float(asset.get('balance', 0)), # Ankr format is often pre-calculated
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
