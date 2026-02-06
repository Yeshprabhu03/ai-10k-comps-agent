import streamlit as st
import pandas as pd
import yfinance as yf
from streamlit_searchbox import st_searchbox
from comps_agent import fetch_and_analyze

# --- Page Configuration ---
st.set_page_config(page_title="IB Comps Agent", layout="wide")

# --- Industry Peer Mapping ---
PEER_MAP = {
    "Consumer Electronics": ["AAPL", "SONY", "HPQ", "DELL", "LNVGY"],
    "Software—Infrastructure": ["MSFT", "ORCL", "ADBE", "SNOW", "PLTR"],
    "Internet Content & Information": ["GOOGL", "META", "SNAP", "PINS", "SPOT"],
    "Consumer Interactive Entertainment": ["MSFT", "SONY", "NTDOY", "EA", "TTWO"],
    "E-Commerce": ["AMZN", "EBAY", "ETSY", "BABA", "MELI"]
}

# --- Ticker Search Logic ---
def search_tickers(searchterm: str):
    if not searchterm or len(searchterm) < 2:
        return []
    try:
        # Queries YFinance Search API for matching tickers/names
        results = yf.Search(searchterm, max_results=5).quotes
        return [(f"{q['symbol']} ({q['shortname']})", q['symbol']) for q in results]
    except:
        return []

# --- UI HEADER ---
st.title("📊 IB Comps Agent")
st.caption("Automated SEC 10-K Benchmarking Dashboard for MBA Financial Analysis")

# --- SIDEBAR: SETTINGS ---
with st.sidebar:
    st.header("Analysis Settings")
    
    # 1. Primary Searchbox
    selected_ticker = st_searchbox(
        search_tickers,
        key="ticker_search",
        label="Search Company Name",
        placeholder="Type 'Apple'..."
    )
    
    # 2. Manual Fallback (Crucial if Search API is slow)
    manual_ticker = st.text_input("OR Type Ticker Manually", value="").upper()
    
    # Final Ticker Determination
    target_ticker = selected_ticker if selected_ticker else manual_ticker

    if target_ticker:
        try:
            # Detect Industry for peer recommendations
            info = yf.Ticker(target_ticker).info
            industry = info.get('industry', "Technology")
            st.info(f"📍 **Industry:** {industry}")
            
            # Suggest peers based on the mapping above
            defaults = PEER_MAP.get(industry, ["MSFT", "GOOGL", "AMZN"])
            peers = st.multiselect(
                "Select Peer Group", 
                options=list(set(defaults + ["META", "TSLA", "NFLX"])), 
                default=defaults[:3]
            )
            
            run_button = st.button("🚀 Generate IB Comps Table", width="stretch")
        except Exception:
            st.error("Ticker not recognized. Please check the symbol.")
            run_button = False
    else:
        st.info("Search a company or type a ticker above to begin.")
        run_button = False

# --- MAIN EXECUTION ---
if run_button:
    all_tickers = [target_ticker] + peers
    
    with st.spinner(f"Accessing SEC EDGAR for {', '.join(all_tickers)}..."):
        # Calls the logic in comps_agent.py
        df = fetch_and_analyze(all_tickers)
    
    if not df.empty:
        st.success("Analysis Complete")
        
        # 1. High-Level Metric Cards
        m_cols = st.columns(len(df))
        for i, row in df.iterrows():
            with m_cols[i]:
                st.metric(
                    row['ticker'], 
                    f"${row['revenue']/1e9:.1f}B", 
                    f"{row['net_margin_%']:.1f}% Margin"
                )
                st.caption(f"10-K Filed: {row['filing_date']}")

        # 2. Detailed Data Table
        st.write("### Financial Comparison Table (USD Millions)")
        st.dataframe(df.style.format({
    'revenue': "${:,.0f}",
    'net_income': "${:,.0f}",
    'ebitda': "${:,.0f}",
    'net_margin_%': "{:.2f}%"
}), width="stretch")
        
        # 3. Export for Excel
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📥 Download CSV for Excel",
            data=csv,
            file_name=f"IB_Comps_{target_ticker}.csv",
            mime='text/csv',
        )
    else:
        st.error("The agent could not extract data. Ensure your API Key and SEC connection are active.")