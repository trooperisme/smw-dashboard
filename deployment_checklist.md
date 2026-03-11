# Deployment Checklist & Setup Guide

Everything has been scaffolded perfectly. Before the dashboard can show live data, you need to plug in the API keys and deploy the resources. Follow these exact steps:

## Phase 1: Supabase (Database) Setup
1. Log into your [Supabase Dashboard](https://supabase.com).
2. Create a new Project.
3. Go to the **SQL Editor**.
4. Copy the entire contents of `schema.sql` and click **Run**.
5. Go to **Project Settings -> API** and copy:
   - `Project URL`
   - `anon` `public` key

## Phase 2: Add API Keys to GitHub 
1. Create a GitHub repository for this project folder (`smw-dashboard`).
2. Go to **Settings -> Secrets and variables -> Actions**.
3. Create the following **New repository secrets**:
   - `SUPABASE_URL`: (from Phase 1)
   - `SUPABASE_KEY`: (from Phase 1)
   - `ALCHEMY_API_KEY`: (Get from [Alchemy Dashboard](https://dashboard.alchemy.com/))
   - `HELIUS_API_KEY`: (Get from [Helius Dashboard](https://dev.helius.xyz/))

*Note: Dexscreener and Ankr do not require API keys for our usage tier.*

## Phase 3: Add Your Wallets
1. Open `data/wallets.csv`.
2. Delete the placeholder rows.
3. Paste in your 520 wallets. Make sure the columns match exactly: `address,cluster_id,chains`. (Chains should be pipe-separated like `ethereum|base`).
4. Commit and push the changes to GitHub.

## Phase 4: Deploy Streamlit
1. Go to [Streamlit Community Cloud](https://share.streamlit.io/).
2. Click **New app** and select your GitHub repository.
3. Set the Main file path to `app.py`.
4. Click **Advanced Settings** and add your Secrets:
   ```toml
   SUPABASE_URL = "your_url_here"
   SUPABASE_KEY = "your_key_here"
   ```
5. Click **Deploy**.

## Phase 5: Trigger the First Ingestion
1. Go to your GitHub Repository -> **Actions** tab.
2. Select **Update Dashboard Data** on the left.
3. Click **Run workflow**.
4. The script will fetch all balances, enrich the data, and update Supabase. After ~5-10 minutes, refresh your Streamlit app to see live "Smart Money" tokens!
