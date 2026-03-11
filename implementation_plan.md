# Implementation Plan: Smart Money Wallet (SMW) Holdings Dashboard

This project aims to build a zero-cost dashboard to track 520 smart money wallets across ETH, Base, SOL, and BSC, using Python, Supabase, and Streamlit.

## User Review Required

> [!IMPORTANT]
> **API Rate Limits:** Helius (Solana) free tier provides 100k credits/month. With updates Every 30 minutes, 520 wallets (if all were SOL) would require ~750k requests/month. Please confirm the number of Solana wallets to ensure we stay within the free tier.

> [!WARNING]
> **Storage Constraints:** Supabase's 500MB limit may be reached quickly if raw snapshots for 520 wallets are stored long-term. I propose an aggregation strategy that purges raw snapshots every 24-48 hours after updating the materialized views.

> [!NOTE]
> **Missing Question:** The project brief included a section "QUESTIONS FOR NEW LLM" which was empty. Please provide any specific questions or concerns you have at this stage.

## Proposed Changes

### [Backend] Data Ingestion Engine
Python scripts running on GitHub Actions every 30 minutes.

- **`fetcher.py`**: Retrieves balances using:
  - `Alchemy API` for ETH and Base.
  - `Ankr RPC` for BSC (completely free and unlimited).
  - `Helius API` for Solana (credits optimized).
- **`metadata.py`**: Fetches market cap and `pairCreatedAt` (Token Age) from `Dexscreener API`.
- **`database.py`**: Handles batch upserts to Supabase to minimize connection overhead.

### [Database] Supabase (PostgreSQL)
Optimized for storage and query speed.

- **`wallet_snapshots`**: Raw data from fetchers (Transient storage).
- **`token_metadata`**: Stores ticker, age, and chains.
- **`aggregated_holdings`**: Materialized view calculating `SMW In` (cluster count) and Total Holdings.

### [Frontend] Streamlit Dashboard
Hosted on Streamlit Cloud.

- **Layout**: Premium Dark theme (following CoinSense aesthetics).
- **Table Columns**:
  - `Token` (Name/Link)
  - `Ticker`
  - `Holdings` (USD value)
  - `Holdings vs Market Cap` (%)
  * `Market Cap` (USD value)
  * `SMW In` (Cluster count)
- **Filters**: 
  - Search bar
  - Min/Max Market Cap inputs
  - Network selector (ETH, Base, SOL, BSC)
- **Interactivity**: Sortable columns and expandable detail views.

## Verification Plan

### Automated Tests
- `pytest` for the ingestion logic (mocking API responses).
- Database migration validation scripts.

### Manual Verification
1. Verify balance fetching for 1 wallet on each chain.
2. Verify Dexscreener data enrichment (Token Age calculation).
3. Verify aggregation logic (ensure clusters are counted correctly).
4. Load test Streamlit filters with 200+ mock tokens.
