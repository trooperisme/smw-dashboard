-- Database Schema for SMW Holdings Dashboard

-- Raw snapshots (Transient - Purged after 24-48h)
CREATE TABLE wallet_snapshots (
    id SERIAL PRIMARY KEY,
    wallet_address TEXT NOT NULL,
    cluster_id INT NOT NULL,
    token_address TEXT NOT NULL,
    ticker TEXT,
    balance_raw NUMERIC,
    balance_usd NUMERIC,
    chain TEXT NOT NULL,
    decimals INT DEFAULT 18,
    captured_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Persistent token metadata
CREATE TABLE token_metadata (
    token_address TEXT PRIMARY KEY,
    token_name TEXT,
    ticker TEXT,
    pair_created_at TIMESTAMP WITH TIME ZONE,
    market_cap NUMERIC,
    liquidity_usd NUMERIC,
    price_usd NUMERIC,
    decimals INT DEFAULT 18,
    chains TEXT[],
    is_honeypot BOOLEAN DEFAULT FALSE,
    buy_tax NUMERIC,
    sell_tax NUMERIC,
    trust_score INT,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Materialized view for dashboard
-- Logic: 
-- 1. Filter out tokens flagged as honeypots
-- 2. Calculate true USD value per cluster using decimals and price
-- NOTE: $1000 minimum is enforced in the Streamlit UI, NOT here,
--       to prevent missing-price tokens from being silently excluded.
CREATE MATERIALIZED VIEW aggregated_holdings AS
WITH cluster_holdings AS (
    SELECT 
        s.token_address,
        s.cluster_id,
        SUM((s.balance_raw / pow(10, COALESCE(s.decimals, 18))) * COALESCE(t.price_usd, 0)) as cluster_total_usd
    FROM 
        wallet_snapshots s
    LEFT JOIN
        token_metadata t ON s.token_address = t.token_address
    WHERE 
        s.captured_at > NOW() - INTERVAL '24 hours'
    GROUP BY 
        s.token_address, s.cluster_id
)
SELECT 
    t.token_name,
    t.ticker,
    t.token_address,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - t.pair_created_at)) / 86400 AS token_age_days,
    t.chains,
    t.is_honeypot,
    t.buy_tax,
    t.sell_tax,
    COUNT(DISTINCT ch.cluster_id) AS smw_in,
    SUM(ch.cluster_total_usd) AS total_holdings_usd,
    t.market_cap,
    (SUM(ch.cluster_total_usd) / NULLIF(t.market_cap, 0)) * 100 AS holdings_mc_pct
FROM 
    token_metadata t
JOIN 
    cluster_holdings ch ON t.token_address = ch.token_address
WHERE 
    t.is_honeypot = FALSE
GROUP BY 
    t.token_address, t.token_name, t.ticker, t.pair_created_at, t.chains, t.market_cap, t.is_honeypot, t.buy_tax, t.sell_tax;

CREATE INDEX idx_token_address ON wallet_snapshots(token_address);
CREATE INDEX idx_captured_at ON wallet_snapshots(captured_at);

-- RPC Function to allow Supabase Python client to refresh the view
CREATE OR REPLACE FUNCTION refresh_aggregated_holdings()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  REFRESH MATERIALIZED VIEW aggregated_holdings;
END;
$$;
