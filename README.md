# SMW Holdings Dashboard

Tracking 520 "Smart Money" wallets across ETH, Base, SOL, and BSC.

## Architecture
- **Ingestion**: Python scripts on GitHub Actions (30-min interval).
- **Database**: Supabase (PostgreSQL) with materialized views for aggregation.
- **Frontend**: Streamlit Cloud ($0 cost).

## Data Sources
- **EVM Balances**: Alchemy API
- **Solana Balances**: Helius API
- **Token Metadata**: Dexscreener API

## Setup
1. Configure Supabase using `schema.sql`.
2. Add API keys to GitHub Secrets.
3. Deploy Streamlit app linked to the Supabase instance.
