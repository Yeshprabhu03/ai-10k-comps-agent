import os
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from streamlit_searchbox import st_searchbox
from comps_agent import fetch_and_analyze

# --- API key check (Streamlit Cloud uses st.secrets, local uses .env) ---
def get_api_key():
    if hasattr(st, "secrets") and st.secrets.get("GOOGLE_API_KEY"):
        return st.secrets["GOOGLE_API_KEY"]
    return os.environ.get("GOOGLE_API_KEY")

# --- Page Configuration ---
st.set_page_config(
    page_title="IB Comps Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
    <style>
    .main-header {
        font-size: 3rem;
        font-weight: 700;
        background: linear-gradient(90deg, #1f77b4, #ff7f0e);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        color: #666;
        font-size: 1.1rem;
        margin-bottom: 2rem;
    }
    .metric-card {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
    .stButton>button {
        width: 100%;
        background: linear-gradient(90deg, #1f77b4, #2ca02c);
        color: white;
        font-weight: 600;
        padding: 0.75rem;
        border-radius: 0.5rem;
        border: none;
    }
    .stButton>button:hover {
        background: linear-gradient(90deg, #1565c0, #1e7e34);
        transform: translateY(-2px);
        box-shadow: 0 4px 8px rgba(0,0,0,0.2);
    }
    </style>
""", unsafe_allow_html=True)

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
        results = yf.Search(searchterm, max_results=8).quotes
        return [(f"{q['symbol']} - {q['shortname']}", q['symbol']) for q in results]
    except:
        return []

# --- Header with Gradient ---
st.markdown('<h1 class="main-header">📊 IB Comps Agent</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Automated SEC 10-K Benchmarking & Investment Banking Valuation Dashboard</p>', unsafe_allow_html=True)

# --- Sidebar: Settings ---
with st.sidebar:
    st.markdown("### ⚙️ Analysis Settings")
    st.markdown("---")
    
    # 1. Primary Search
    selected_ticker = st_searchbox(
        search_tickers,
        key="ticker_search",
        label="🔍 Search Company",
        placeholder="Type 'Apple' or 'AAPL'...",
        default=None
    )
    
    # 2. Manual Fallback
    st.markdown("**OR**")
    manual_ticker = st.text_input(
        "📝 Enter Ticker Symbol",
        value="",
        placeholder="e.g., AAPL, MSFT, GOOGL",
        help="Type the stock ticker symbol directly"
    ).upper().strip()
    
    target_ticker = selected_ticker if selected_ticker else manual_ticker

    if target_ticker:
        try:
            # Fetch company info
            ticker_obj = yf.Ticker(target_ticker)
            info = ticker_obj.info
            
            # Display company info card
            st.markdown("---")
            st.markdown("### 📋 Company Info")
            
            company_name = info.get('longName', target_ticker)
            industry = info.get('industry', 'N/A')
            sector = info.get('sector', 'N/A')
            
            st.markdown(f"**{company_name}**")
            st.caption(f"Ticker: **{target_ticker}**")
            
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Industry", industry[:20] + "..." if len(industry) > 20 else industry)
            with col2:
                st.metric("Sector", sector[:15] + "..." if len(sector) > 15 else sector)
            
            # Peer selection
            st.markdown("---")
            st.markdown("### 👥 Peer Selection")
            
            # Get suggested peers based on industry
            suggested_peers = PEER_MAP.get(industry, ["MSFT", "GOOGL", "AMZN"])
            all_options = list(set(suggested_peers + ["META", "TSLA", "NFLX", "NVDA", "AMD", "INTC"]))
            
            peers = st.multiselect(
                "Select Comparable Companies",
                options=all_options,
                default=suggested_peers[:3] if len(suggested_peers) >= 3 else suggested_peers,
                help="Select companies to compare against"
            )
            
            if not peers:
                st.warning("⚠️ Please select at least one peer company")
            
            st.markdown("---")
            run_button = st.button("🚀 Generate Comps Analysis", use_container_width=True, type="primary")
            
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            st.info("Please check the ticker symbol and try again.")
            run_button = False
    else:
        st.info("👆 Search for a company or enter a ticker symbol to begin analysis.")
        run_button = False

# --- Main Content Area ---
if run_button and target_ticker:
    all_tickers = [target_ticker] + peers
    
    if not peers:
        st.warning("⚠️ Please select at least one peer company in the sidebar.")
        st.stop()
    
    # 0. Ensure API key is set (required for Gemini in comps_agent)
    api_key = get_api_key()
    if not api_key or not str(api_key).strip():
        st.error(
            "**Google API key is missing.** "
            "On Streamlit Cloud: add `GOOGLE_API_KEY` in **Settings → Secrets**. "
            "Locally: add it to your `.env` file."
        )
        st.stop()
    
    # 1. Fetch SEC Data
    with st.spinner("Extracting 10-K data..."):
        try:
            df = fetch_and_analyze(all_tickers)
        except Exception as e:
            err_msg = str(e).lower()
            if "api key" in err_msg or "invalid_argument" in err_msg or "401" in err_msg:
                st.error(
                    "**Invalid or missing Google API key.** "
                    "Check **Streamlit Cloud → Settings → Secrets** (or `.env` locally) and set a valid `GOOGLE_API_KEY`."
                )
            else:
                st.error(f"❌ Error fetching SEC data: {str(e)}")
            st.stop()
    
    # 2. Safety check: ensure the SEC agent actually returned data (avoids KeyError: 'ticker')
    if df is None:
        df = pd.DataFrame()
    if not isinstance(df, pd.DataFrame) or df.empty or "ticker" not in getattr(df, "columns", []):
        st.error(
            "The SEC Agent could not find data for these tickers. "
            "This often happens when the Google API key is invalid or missing (check Secrets). "
            "Otherwise check ticker symbols and filing availability."
        )
        st.stop()
    
    # 3. Fetch Real-time Market Data for Valuation
    with st.spinner("Calculating Valuation Multiples..."):
        val_data = []
        for t in all_tickers:
            try:
                stock = yf.Ticker(t)
                mkt_cap = stock.info.get("marketCap", 0)
                enterprise_value = stock.info.get("enterpriseValue", mkt_cap)
                val_data.append({"ticker": t, "mkt_cap": mkt_cap, "enterprise_value": enterprise_value})
            except Exception:
                val_data.append({"ticker": t, "mkt_cap": 0, "enterprise_value": 0})
        
        val_df = pd.DataFrame(val_data)
        try:
            df = df.merge(val_df, on="ticker", how="inner")
        except KeyError:
            st.error("The SEC Agent could not find data for these tickers. Please check the spelling or filing availability.")
            st.stop()
    
    # 4. Calculate valuation metrics (only if we have rows)
    if df.empty:
        st.warning("SEC data was found but no market data could be loaded for these tickers. Check symbols or try again.")
        st.stop()
    
    # Normalize to USD millions if backend sent dollars (e.g. value > 1e8)
    for col in ["revenue", "net_income", "ebitda"]:
        df[col] = df[col].apply(lambda x: x / 1e6 if x and abs(x) > 1e8 else (x if x else 0))
    # Revenue, net_income, ebitda are in USD millions; mkt_cap/enterprise_value are in dollars
    rev_dollars = df["revenue"] * 1e6
    ni_dollars = df["net_income"] * 1e6
    ebitda_dollars = df["ebitda"] * 1e6
    df["P/E_Ratio"] = (df["mkt_cap"] / ni_dollars).replace([float("inf"), float("-inf")], 0).fillna(0)
    df["EV/Revenue"] = (df["enterprise_value"] / rev_dollars).replace([float("inf"), float("-inf")], 0).fillna(0)
    df["EV/EBITDA"] = (df["enterprise_value"] / ebitda_dollars).replace([float("inf"), float("-inf")], 0).fillna(0)
    df["P/S_Ratio"] = (df["mkt_cap"] / rev_dollars).replace([float("inf"), float("-inf")], 0).fillna(0)

    if not df.empty:
        st.success(f"✅ Analysis complete! Processed {len(df)} companies.")
        
        # --- Key Metrics Cards ---
        st.markdown("### 📈 Key Financial Metrics")
        metric_cols = st.columns(len(df))
        
        for idx, (i, row) in enumerate(df.iterrows()):
            with metric_cols[idx]:
                st.markdown(f"#### {row['ticker']}")
                # Data is in USD millions; /1000 = billions. Guard: if value huge, treat as dollars and use /1e9
                rev = row["revenue"]
                rev_b = rev / 1000 if rev < 1e8 else rev / 1e9
                st.metric(
                    "Revenue",
                    f"${rev_b:.2f}B",
                    delta=f"{row['net_margin_%']:.1f}% Margin"
                )
                col_a, col_b = st.columns(2)
                with col_a:
                    pe = row["P/E_Ratio"]
                    st.metric("P/E", f"{pe:.1f}x" if pe and pe > 0 else "N/A")
                with col_b:
                    evr = row["EV/Revenue"]
                    st.metric("EV/Rev", f"{evr:.2f}x" if evr and evr > 0 else "N/A")
                st.caption(f"Filed: {row['filing_date']}")
        
        st.markdown("---")
        
        # --- Visualizations ---
        st.markdown("### 📊 Comparative Analysis")
        
        viz_tabs = st.tabs(["📈 Revenue Comparison", "💰 Profitability", "💵 Valuation Multiples", "📋 Full Data Table"])
        
        with viz_tabs[0]:
            # Revenue Bar Chart (revenue in USD millions)
            plot_df = df[["ticker", "revenue"]].copy().fillna(0)
            plot_df = plot_df.loc[plot_df["revenue"] > 0].sort_values("revenue", ascending=False)
            if not plot_df.empty:
                fig_rev = px.bar(
                    plot_df,
                    x="ticker",
                    y="revenue",
                    title="Revenue Comparison (USD Millions)",
                    labels={"revenue": "Revenue (USD Millions)", "ticker": "Company"},
                    color="revenue",
                    color_continuous_scale="Blues"
                )
                fig_rev.update_layout(showlegend=False, height=400)
                st.plotly_chart(fig_rev, use_container_width=True)
            else:
                st.info("No revenue data to display.")
        
        with viz_tabs[1]:
            # Profitability Metrics
            col1, col2 = st.columns(2)
            plot_df_m = df[["ticker", "net_margin_%"]].copy().fillna(0)
            plot_df_e = df[["ticker", "ebitda"]].copy().fillna(0)
            with col1:
                if not plot_df_m.empty:
                    fig_margin = px.bar(
                        plot_df_m.sort_values("net_margin_%", ascending=False),
                        x="ticker",
                        y="net_margin_%",
                        title="Net Margin %",
                        labels={"net_margin_%": "Net Margin (%)", "ticker": "Company"},
                        color="net_margin_%",
                        color_continuous_scale="Greens"
                    )
                    fig_margin.update_layout(showlegend=False, height=350)
                    st.plotly_chart(fig_margin, use_container_width=True)
                else:
                    st.info("No margin data.")
            with col2:
                if not plot_df_e.empty and plot_df_e["ebitda"].gt(0).any():
                    fig_ebitda = px.bar(
                        plot_df_e.sort_values("ebitda", ascending=False),
                        x="ticker",
                        y="ebitda",
                        title="EBITDA (USD Millions)",
                        labels={"ebitda": "EBITDA (USD Millions)", "ticker": "Company"},
                        color="ebitda",
                        color_continuous_scale="Oranges"
                    )
                    fig_ebitda.update_layout(showlegend=False, height=350)
                    st.plotly_chart(fig_ebitda, use_container_width=True)
                else:
                    st.info("No EBITDA data.")
        
        with viz_tabs[2]:
            # Valuation Multiples
            val_metrics = ["P/E_Ratio", "EV/Revenue", "EV/EBITDA", "P/S_Ratio"]
            val_df_plot = df[["ticker"] + val_metrics].copy()
            val_df_plot[val_metrics] = val_df_plot[val_metrics].replace([float("inf"), float("-inf")], 0).fillna(0)
            # Clip extreme multiples for readable chart (e.g. cap at 99th percentile or 100)
            for m in val_metrics:
                q = val_df_plot[m].replace(0, float("nan")).quantile(0.99)
                cap = q if pd.notna(q) and q > 0 else 100
                val_df_plot[m] = val_df_plot[m].clip(upper=cap)
            if val_df_plot[val_metrics].abs().max().max() > 0:
                fig_val = px.bar(
                    val_df_plot,
                    x="ticker",
                    y=val_metrics,
                    title="Valuation Multiples Comparison",
                    labels={"value": "Multiple", "ticker": "Company", "variable": "Metric"},
                    barmode="group"
                )
                fig_val.update_layout(height=450)
                st.plotly_chart(fig_val, use_container_width=True)
            else:
                st.info("No valuation multiples (market cap may be missing from yfinance).")
        
        with viz_tabs[3]:
            # Financial Comparison Table (USD Millions) — whole numbers
            st.markdown("#### Financial Comparison Table (USD Millions)")
            display_df = df.copy()
            # Values in USD millions; show as whole numbers (e.g. 716,924)
            display_df["revenue_fmt"] = display_df["revenue"].apply(lambda x: f"{float(x):,.0f}" if x is not None and not (isinstance(x, float) and (x != x)) else "—")
            display_df["net_income_fmt"] = display_df["net_income"].apply(lambda x: f"{float(x):,.0f}" if x is not None and not (isinstance(x, float) and (x != x)) else "—")
            display_df["ebitda_fmt"] = display_df["ebitda"].apply(lambda x: f"{float(x):,.0f}" if x is not None and not (isinstance(x, float) and (x != x)) else "—")
            display_df["mkt_cap_fmt"] = display_df["mkt_cap"].apply(lambda x: f"${x/1e9:.2f}B" if x > 0 else "N/A")
            display_df["net_margin_%_fmt"] = display_df["net_margin_%"].apply(lambda x: f"{x:.2f}%")
            display_df["P/E_Ratio_fmt"] = display_df["P/E_Ratio"].apply(lambda x: f"{x:.1f}x" if x > 0 else "N/A")
            display_df["EV/Revenue_fmt"] = display_df["EV/Revenue"].apply(lambda x: f"{x:.2f}x" if x > 0 else "N/A")
            display_df["EV/EBITDA_fmt"] = display_df["EV/EBITDA"].apply(lambda x: f"{x:.2f}x" if x > 0 else "N/A")
            
            out = display_df[["ticker", "filing_date", "revenue_fmt", "net_income_fmt", "ebitda_fmt",
                              "net_margin_%_fmt", "mkt_cap_fmt", "P/E_Ratio_fmt", "EV/Revenue_fmt", "EV/EBITDA_fmt"]].copy()
            out.columns = ["Ticker", "Filing Date", "Revenue (USD Millions)", "Net Income (USD Millions)", "EBITDA (USD Millions)",
                           "Net Margin %", "Market Cap", "P/E", "EV/Revenue", "EV/EBITDA"]
            st.dataframe(out, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # --- Export Section ---
        st.markdown("### 💾 Export Data")
        col_exp1, col_exp2 = st.columns(2)
        
        with col_exp1:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                "📥 Download CSV (Excel-ready)",
                data=csv,
                file_name=f"IB_Comps_{target_ticker}_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
                mime='text/csv',
                use_container_width=True
            )
        
        with col_exp2:
            st.info(f"📊 **{len(df)}** companies analyzed | Generated on {pd.Timestamp.now().strftime('%B %d, %Y at %I:%M %p')}")
    
    else:
        st.error("❌ The analysis could not extract data. Please check:")
        st.markdown("""
        - Your API key is valid and active
        - SEC EDGAR connection is working
        - Ticker symbols are correct
        - Companies have recent 10-K filings
        """)