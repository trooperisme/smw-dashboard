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
    chains TEXT[],
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Materialized view for dashboard
CREATE MATERIALIZED VIEW aggregated_holdings AS
SELECT 
    t.token_name,
    t.ticker,
    t.token_address,
    EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - t.pair_created_at)) / 86400 AS token_age_days,
    t.chains,
    COUNT(DISTINCT s.cluster_id) AS smw_in,
    SUM(s.balance_usd) AS total_holdings_usd,
    t.market_cap,
    (SUM(s.balance_usd) / NULLIF(t.market_cap, 0)) * 100 AS holdings_mc_pct
FROM 
    token_metadata t
JOIN 
    wallet_snapshots s ON t.token_address = s.token_address
WHERE 
    s.captured_at > NOW() - INTERVAL '1 hour'
GROUP BY 
    t.token_address, t.token_name, t.ticker, t.pair_created_at, t.chains, t.market_cap;

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
