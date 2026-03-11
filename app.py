import streamlit as st
import pandas as pd
from supabase import create_client
import os

st.set_page_config(
    page_title="SMW Holdings Dashboard",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for dark premium theme
st.markdown("""
<style>
    .stApp {
        background-color: #0d1117;
        color: #c9d1d9;
    }
    .stMetric {
        background-color: #161b22;
        padding: 15px;
        border-radius: 8px;
        border: 1px solid #30363d;
    }
    div[data-testid="stSidebar"] {
        background-color: #161b22;
        border-right: 1px solid #30363d;
    }
    div[data-testid="stDataFrame"] {
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_supabase():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        st.warning("Database configuration missing (SUPABASE_URL/SUPABASE_KEY). Using placeholder data.")
        return None
    return create_client(url, key)

supabase = init_supabase()

@st.cache_data(ttl=1800)
def load_data():
    if not supabase:
        # Provide placeholder for UI development if keys missing
        return pd.DataFrame()
        
    try:
        response = supabase.table('aggregated_holdings').select('*').execute()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

# Main Header
st.title("💎 Smart Money Holdings DEX")

# Sidebar
st.sidebar.header("Filter Signals")

df = load_data()

# Render UI even if DF is empty for scaffolding purposes
if df.empty:
    st.info("No data available or Database not connected. Awaiting data ingestion pipeline.")
    df = pd.DataFrame(columns=[
        'token_name', 'ticker', 'token_age_days', 'chains',
        'smw_in', 'total_holdings_usd', 'market_cap', 'holdings_mc_pct'
    ])

# Filters
col_search, col_min, col_max, col_chain = st.columns(4)

with col_search:
    search_term = st.text_input("🔍 Search Token or Ticker", "")

with col_min:
    min_mcap = st.number_input("Min Market Cap ($)", value=0, format="%d")

with col_max:
    max_mcap = st.number_input("Max Market Cap ($)", value=1_000_000_000, format="%d")

with col_chain:
    selected_chains = st.multiselect(
        "Networks",
        options=['ethereum', 'base', 'solana', 'bsc'],
        default=['ethereum', 'base', 'solana', 'bsc']
    )

st.sidebar.markdown("---")
min_smw = st.sidebar.slider("Min SMW Clusters", min_value=1, max_value=26, value=1)
min_age = st.sidebar.number_input("Min Age (Days)", value=0)
max_age = st.sidebar.number_input("Max Age (Days)", value=365)


# Apply Filter Logic
filtered_df = df.copy()
if not filtered_df.empty:
    filtered_df = filtered_df[
        (filtered_df['market_cap'] >= min_mcap) &
        (filtered_df['market_cap'] <= max_mcap) &
        (filtered_df['smw_in'] >= min_smw)
    ]
    
    # Age filter (handle nulls if any)
    filtered_df = filtered_df[
        filtered_df['token_age_days'].isna() | 
        ((filtered_df['token_age_days'] >= min_age) & (filtered_df['token_age_days'] <= max_age))
    ]
    
    # Chain Filter
    if selected_chains:
        # Assuming chains is a list in DB
        filtered_df = filtered_df[filtered_df['chains'].apply(
            lambda row_chains: any(c in selected_chains for c in (row_chains or []))
        )]
        
    if search_term:
        term = search_term.lower()
        filtered_df = filtered_df[
            filtered_df['token_name'].str.lower().str.contains(term, na=False) |
            filtered_df['ticker'].str.lower().str.contains(term, na=False)
        ]

# Top Metrics
m1, m2, m3 = st.columns(3)
m1.metric("Tracked Tokens", len(filtered_df))
m2.metric("Total Holdings", f"${filtered_df['total_holdings_usd'].sum():,.0f}" if not filtered_df.empty else "$0")
m3.metric("Avg SMW Concentration", f"{filtered_df['smw_in'].mean():.1f}" if not filtered_df.empty else "0.0")

st.markdown("---")

# Format Table
if not filtered_df.empty:
    display_df = filtered_df[[
        'token_name', 'ticker', 'total_holdings_usd', 'holdings_mc_pct', 
        'market_cap', 'smw_in', 'token_age_days', 'chains'
    ]].copy()
    
    # Clean output
    display_df['chains'] = display_df['chains'].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
    display_df['total_holdings_usd'] = display_df['total_holdings_usd'].apply(lambda x: f"${x:,.2f}")
    display_df['market_cap'] = display_df['market_cap'].apply(lambda x: f"${x:,.0f}" if pd.notnull(x) else "N/A")
    display_df['holdings_mc_pct'] = display_df['holdings_mc_pct'].apply(lambda x: f"{x:.4f}%" if pd.notnull(x) else "N/A")
    display_df['token_age_days'] = display_df['token_age_days'].apply(lambda x: f"{x:.1f}" if pd.notnull(x) else "N/A")
    
    display_df.columns = [
        'Token', 'Ticker', 'Holdings', 'Holdings vs MC %', 
        'Market Cap', 'SMW In', 'Age (Days)', 'Chains'
    ]
    
    # Sort by Holdings by default
    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        height=600
    )
    
    st.download_button(
        label="📥 Export Data",
        data=filtered_df.to_csv(index=False),
        file_name="smw_holdings_export.csv",
        mime="text/csv"
    )
