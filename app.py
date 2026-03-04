import os
import streamlit as st
import pandas as pd
import yfinance as yf
import plotly.express as px
import plotly.graph_objects as go
from streamlit_searchbox import st_searchbox
from comps_agent import fetch_and_analyze, get_all_sec_tickers
from google import genai

# --- API key check (Streamlit Cloud uses st.secrets, local uses .env) ---
def get_api_key():
    try:
        if hasattr(st, "secrets") and st.secrets.get("GOOGLE_API_KEY"):
            return st.secrets["GOOGLE_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GOOGLE_API_KEY")

# --- Page Configuration ---
st.set_page_config(
    page_title="IB Comps Agent",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for Premium IB Aesthetics
st.markdown("""
    <style>
    /* Global Background and Text */
    .stApp {
        background-color: #000000;
        color: #e0e0e0;
        font-family: monospace;
    }
    
    /* Header Typography */
    .main-header {
        font-size: 2.2rem;
        font-weight: 800;
        color: #FF8C00;
        margin-bottom: 0.2rem;
        letter-spacing: 1px;
        text-transform: uppercase;
        border-bottom: 2px solid #FF8C00;
        padding-bottom: 5px;
    }
    .sub-header {
        color: #a0a0a0;
        font-size: 1.0rem;
        font-weight: 400;
        margin-bottom: 2.0rem;
        font-family: monospace;
    }
    
    /* High Density Expanders & Containers */
    div[data-testid="stExpander"] {
        background: #0a0a0a;
        border: 1px solid #333333;
        border-radius: 0px;
    }
    
    /* Sleek Primary Buttons */
    .stButton>button[kind="primary"] {
        width: 100%;
        background-color: #FF8C00;
        color: #000000;
        font-weight: 800;
        letter-spacing: 0.5px;
        padding: 0.5rem;
        border-radius: 2px;
        border: 1px solid #FF8C00;
        transition: none;
        text-transform: uppercase;
    }
    .stButton>button[kind="primary"]:hover {
        background-color: #000000;
        color: #FF8C00;
        border: 1px solid #FF8C00;
    }
    
    /* Secondary Buttons */
    .stButton>button[kind="secondary"] {
        border-radius: 2px;
        border: 1px solid #555555;
        background-color: #1a1a1a;
        color: #ffffff;
        text-transform: uppercase;
        font-size: 0.9rem;
    }
    .stButton>button[kind="secondary"]:hover {
        background-color: #333333;
        border-color: #ffffff;
    }
    </style>
""", unsafe_allow_html=True)

# --- SEC Ticker Loader (cached for 8,000+ U.S. companies) ---
@st.cache_data(ttl=3600)
def _load_sec_tickers():
    return get_all_sec_tickers()

# --- AI Peer Suggestions ---
@st.cache_data(ttl=86400, show_spinner=False)
def _get_ai_peer_suggestions(company_name: str, industry: str, sector: str, api_key: str):
    """Uses Gemini to instantly suggest 5 relevant peer tickers."""
    if not api_key or industry == "N/A":
        return []
    try:
        client = genai.Client(api_key=api_key)
        prompt = f"Given the public company '{company_name}' operating in the '{industry}' industry and '{sector}' sector, return exactly 5 US stock ticker symbols for its closest publicly traded competitors. Return ONLY the ticker symbols separated by commas. Do not include any other text."
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        tickers = [t.strip().upper() for t in response.text.split(",") if t.strip()]
        return tickers[:5]
    except Exception:
        return []

def _fetch_ma_deals(ticker: str):
    """Fetches M&A deals dynamically by natively executing the ma_service python module."""
    import streamlit as st
    import asyncio
    try:
        from ma_service import get_recent_ma_deals
        
        # Create a new event loop so Streamlit can run the async function natively
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Natively execute the M&A feature without using port 8000
        response = loop.run_until_complete(get_recent_ma_deals(ticker))
        
        if response.status == "Success":
            # Convert Pydantic objects back into dicts for the Streamlit UI
            return [dict(d) for d in response.deals]
        else:
            st.error(f"Backend Engine Returned: {response.status}")
            
    except Exception as e:
        st.error(f"Critical Native Execution Exception: {str(e)}")
        print(f"M&A Service internal execution error: {e}")
    return []


def search_tickers_sec(searchterm: str):
    """Searchable dropdown: suggests as you type (SEC list, or yfinance fallback)."""
    searchterm = (searchterm or "").strip()
    if not searchterm:
        return []
    s = searchterm.upper()
    tickers = _load_sec_tickers()
    if tickers:
        # Match by ticker or company name (substring); rank prefix matches first
        scored = []
        for ticker, name in tickers:
            name_upper = (name or "").upper()
            if s not in ticker and s not in name_upper:
                continue
            if ticker.startswith(s) or name_upper.startswith(s):
                score = 0  # prefix: show first
            elif s in ticker or s in name_upper:
                score = 1  # substring
            else:
                continue
            scored.append((score, f"{ticker} - {name}", ticker))
        scored.sort(key=lambda x: (x[0], x[2]))
        return [(label, ticker) for _, label, ticker in scored[:50]]
    # Fallback when SEC list empty (e.g. network): use yfinance
    try:
        results = yf.Search(searchterm, max_results=15).quotes
        return [(f"{q['symbol']} - {q['shortname']}", q['symbol']) for q in results]
    except Exception:
        return []

# --- Header with Gradient ---
st.markdown('<h1 class="main-header">📊 IB Comps Agent</h1>', unsafe_allow_html=True)
st.markdown('<p class="sub-header">Automated SEC 10-K Benchmarking & Investment Banking Valuation Dashboard</p>', unsafe_allow_html=True)

if "app_mode" not in st.session_state:
    st.session_state.app_mode = "home"

if st.session_state.app_mode == "home":
    st.markdown("<br><br>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 8, 1])
    with c2:
        st.markdown("### Select Module")
        col_A, col_B = st.columns(2)
        with col_A:
            st.markdown("""
            <div style="border: 1px solid #444; border-radius: 8px; padding: 20px; text-align: center; background: #111;">
                <h2 style="color: #FF8C00; margin-bottom: 5px;">📈 IB Comps</h2>
                <p style="color: #ccc; font-size: 0.9rem;">Run relative valuation against U.S. public peers.</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Launch Comps Engine", use_container_width=True, type="primary"):
                st.session_state.app_mode = "comps"
                st.rerun()
        with col_B:
            st.markdown("""
            <div style="border: 1px solid #444; border-radius: 8px; padding: 20px; text-align: center; background: #111;">
                <h2 style="color: #00d2ff; margin-bottom: 5px;">🤝 M&A Deals</h2>
                <p style="color: #ccc; font-size: 0.9rem;">Track live M&A deal advisors using News RAG.</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button("Launch M&A Tracker", use_container_width=True, type="primary"):
                st.session_state.app_mode = "m_and_a"
                st.rerun()
    st.stop()

if st.button("⬅️ Back to Home"):
    st.session_state.app_mode = "home"
    st.rerun()

st.markdown("---")

if st.session_state.app_mode == "m_and_a":
    st.markdown("## 🤝 Live M&A Deal Tracker")
    st.markdown("Powered by Google Gemini 2.5 News RAG Architecture.")
    
    ma_ticker = st_searchbox(
        search_tickers_sec,
        key="ma_ticker_search",
        label="🔍 Search Target Company (SEC list)",
        placeholder="Type 'Microsoft' or 'MSFT'...",
        default=None
    )
    
    if ma_ticker:
        st.markdown(f"**Live M&A Deal Tracker for {ma_ticker}**")
        with st.spinner("Pinging FastAPI Microservice..."):
            deals = _fetch_ma_deals(ma_ticker)
            
        if deals:
            for d in deals:
                st.markdown(f"#### {d.get('deal_name', 'Unknown Deal')}")
                st.caption(f"**Value:** {d.get('deal_value', 'Undisclosed')}")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Target", d.get('target_company', 'N/A'))
                c2.metric("Acquirer", d.get('acquirer_company', 'N/A'))
                c3.metric("Buy-Side Advisors", d.get('buy_side_advisors', 'N/A'))
                c4.metric("Sell-Side Advisors", d.get('sell_side_advisors', 'N/A'))
                st.divider()
        else:
            st.info("No recent M&A activity found or Microservice is offline. Ensure you are running `uvicorn ma_service:app --port 8000` in a separate terminal.")
            
    st.stop()

# --- Settings Expander for Comps Mode ---
if "peer_list" not in st.session_state:
    st.session_state.peer_list = []
if "run_analysis" not in st.session_state:
    st.session_state.run_analysis = False

with st.expander("⚙️ Analysis Settings", expanded=True):
    st.markdown("Select a primary target and up to 5 peers for comparable analysis.")
    col_set1, col_set2 = st.columns(2)
    
    with col_set1:
        # 1. Primary company: searchable SEC dropdown (entire U.S. market)
        selected_ticker = st_searchbox(
            search_tickers_sec,
            key="ticker_search",
            label="🔍 Search Company (SEC list)",
            placeholder="Type 'Apple' or 'AAPL'... (8,000+ companies)",
            default=None
        )
        
        target_ticker = selected_ticker
        
        # --- Move Peer Selection here to save space ---
        st.markdown("---")
        st.markdown("### 👥 Peer Selection")
        _load_sec_tickers()  # Preload
        add_peer = st_searchbox(
            search_tickers_sec,
            key="peer_search",
            label="Search to add competitor",
            placeholder="e.g. Microsoft, GOOGL...",
            default=None
        )
        if add_peer and add_peer not in st.session_state.peer_list:
            st.session_state.peer_list = list(st.session_state.peer_list) + [add_peer]
            
        if st.session_state.peer_list:
            for i, p in enumerate(st.session_state.peer_list):
                c1, c2 = st.columns([3, 1])
                # Lookup full company name
                sec_list = _load_sec_tickers()
                comp_name = next((n for t, n in sec_list if t == p), p)
                # Truncate length if too long
                comp_name = comp_name[:25] + "..." if len(comp_name) > 25 else comp_name
                
                with c1:
                    st.caption(f"**{p}** - {comp_name}")
                with c2:
                    if st.button("REMOVE", key=f"rm_{p}_{i}"):
                        st.session_state.peer_list = [x for x in st.session_state.peer_list if x != p]
                        st.rerun()
            if st.button("CLEAR ALL"):
                st.session_state.peer_list = []
                st.rerun()
                
        peers = list(st.session_state.peer_list)
        if not peers:
            st.warning("⚠️ Add at least one peer above")
            
        st.markdown("---")
        run_btn = st.button("🚀 GENERATE COMPS ANALYSIS", use_container_width=True, type="primary")
        if run_btn:
            st.session_state.run_analysis = True

    if target_ticker:
        try:
            ticker_obj = yf.Ticker(target_ticker)
            
            # Use safe lookup to avoid 429 errors crashing the whole app
            company_name = target_ticker
            industry = "N/A"
            sector = "N/A"
            try:
                # Try getting fast_info first for speed
                f_info = ticker_obj.fast_info
                # Attempt to get full info but fail silently if rate limited
                full_info = ticker_obj.info
                company_name = full_info.get("longName", target_ticker)
                industry = full_info.get("industry", "N/A")
                sector = full_info.get("sector", "N/A")
            except Exception:
                pass
            
            with col_set2:
                st.markdown("### 📋 Company Info")
                st.markdown(f"**{company_name}**")
                st.caption(f"Ticker: **{target_ticker}**")
                c1, c2 = st.columns(2)
                with c1:
                    st.metric("Industry", industry[:20] + "..." if len(industry) > 20 else industry)
                with c2:
                    st.metric("Sector", sector[:15] + "..." if len(sector) > 15 else sector)
                
                # --- AI Smart Peer Injection ---
                api_key = get_api_key()
                if api_key and industry != "N/A":
                    st.markdown("---")
                    st.caption("🤖 **AI Suggested Peers:**")
                    suggested_peers = _get_ai_peer_suggestions(company_name, industry, sector, api_key)
                    
                    if suggested_peers:
                        # Display as highly compact row of buttons
                        peer_cols = st.columns(len(suggested_peers))
                        for i, peer_ticker in enumerate(suggested_peers):
                            with peer_cols[i]:
                                if st.button(f"+ {peer_ticker}", key=f"ai_add_{peer_ticker}"):
                                    if peer_ticker not in st.session_state.peer_list:
                                        st.session_state.peer_list = list(st.session_state.peer_list) + [peer_ticker]
                                        st.rerun()
            
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            st.info("Check the ticker symbol and try again.")
    else:
        with col_set2:
            st.info("👆 Search for a company (SEC list) or enter a ticker to begin.")

# --- Main Content Area ---
if st.session_state.run_analysis and target_ticker:
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
    
    # 1. Fetch SEC Data (skips tickers with no 10-K/20-F gracefully)
    @st.cache_data(ttl=3600, show_spinner=False)
    def cached_fetch_and_analyze(tickers_tuple):
        return fetch_and_analyze(list(tickers_tuple))
        
    with st.spinner("Extracting 10-K data..."):
        try:
            # Pass as tuple since lists are unhashable for st.cache_data
            df = cached_fetch_and_analyze(tuple(all_tickers))
            skipped = [t for t in all_tickers if t not in df["ticker"].values]
            if skipped:
                st.warning(f"Skipped (no 10-K/20-F or error): **{', '.join(skipped)}**")
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
        
        static_fx = {"JPY": 0.0067, "EUR": 1.08, "GBP": 1.25, "CAD": 0.74, "CHF": 1.13, "AUD": 0.65}
        
        for t in all_tickers:
            try:
                stock = yf.Ticker(t)
                # Use fast_info - much less prone to rate limiting than .info
                f_info = stock.fast_info
                
                # fast_info is an object, not a dict, so use getattr
                mkt_cap = getattr(f_info, "market_cap", 0)
                
                # Check for currency mismatch and convert mkt_cap to USD
                quote_currency = getattr(f_info, "currency", "USD")
                if quote_currency != "USD" and mkt_cap > 0:
                    fx_to_usd = 1.0
                    try:
                        if quote_currency == 'JPY':
                            fx_to_usd = 1.0 / float(yf.Ticker("USDJPY=X").history(period="1d")["Close"].iloc[-1])
                        elif quote_currency == 'EUR':
                            fx_to_usd = float(yf.Ticker("EURUSD=X").history(period="1d")["Close"].iloc[-1])
                        else:
                            fx_to_usd = float(yf.Ticker(f"{quote_currency}USD=X").history(period="1d")["Close"].iloc[-1])
                    except Exception:
                        fx_to_usd = static_fx.get(quote_currency, 1.0)
                    
                    mkt_cap = mkt_cap * fx_to_usd
                
                # EV = Market Cap + Total Liabilities (ignoring cash for simplicity given SEC constraints)
                enterprise_value = mkt_cap
                try:
                    sec_row = df[df["ticker"] == t].iloc[0]
                    # The total liab from DF is already in USD Millions
                    total_liab_usd = sec_row.get("total_liabilities", 0) * 1e6
                    if total_liab_usd > 0:
                        enterprise_value = mkt_cap + total_liab_usd
                except Exception:
                    pass

                val_data.append({"ticker": t, "mkt_cap": mkt_cap, "enterprise_value": enterprise_value})
            except Exception as e:
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
        
        # --- Key Metrics Cards (High-Density UI Revamp) ---
        st.markdown("### 📈 Financial Snapshot Overview")
        st.caption("High-density comparative metrics formatted for standard IB screening.")
        
        # Build a consolidated dataframe for the view
        snap_data = []
        sec_list = _load_sec_tickers()
        
        for idx, row in df.iterrows():
            rev = row["revenue"]
            rev_b = rev / 1000 if rev < 1e8 else rev / 1e9
            
            # Fetch full company name
            tick = row["ticker"]
            comp_name = next((n for t, n in sec_list if t == tick), tick)
            
            # If the SEC list failed entirely (e.g. SSL block) or missing, fallback to yfinance Search
            if comp_name == tick:
                try:
                    search_res = yf.Search(tick, max_results=1).quotes
                    if search_res:
                        comp_name = search_res[0].get("shortname", tick)
                except Exception:
                    pass
            
            # Force explicit string conversion of UNIX epoch dates for Streamlit rendering
            filing_date_val = row["filing_date"]
            if str(filing_date_val).isdigit() or isinstance(filing_date_val, (int, float)):
                # Handle Pandas converting Timestamp to 177... ms epoch in Streamlit 1.4+
                try:
                    filing_date_val = pd.to_datetime(filing_date_val, unit='ms').strftime('%Y-%m-%d')
                except Exception:
                    pass
            
            snap_data.append({
                "Company": f"{tick} - {comp_name[:30] + '...' if len(comp_name) > 30 else comp_name}",
                "Revenue ($B)": rev_b,
                "Net Margin (%)": row["net_margin_%"],
                "P/E": row["P/E_Ratio"] if row["P/E_Ratio"] > 0 else None,
                "EV/Rev": row["EV/Revenue"] if row["EV/Revenue"] > 0 else None,
                "Filing Date": filing_date_val,
                "FY": str(row.get("fiscal_year", ""))
            })
            
        snap_df = pd.DataFrame(snap_data)
        
        st.dataframe(
            snap_df,
            column_config={
                "Company": st.column_config.TextColumn("Company", width="large"),
                "Revenue ($B)": st.column_config.NumberColumn("Revenue", format="$%.2f B", width="medium"),
                "Net Margin (%)": st.column_config.ProgressColumn(
                    "Profit Margin",
                    help="Company Net Income Margin %",
                    format="%.1f %%",
                    min_value=0,
                    max_value=max(100, snap_df["Net Margin (%)"].max() if not snap_df.empty else 100),
                ),
                "P/E": st.column_config.NumberColumn("P/E Ratio", format="%.1f x"),
                "EV/Rev": st.column_config.NumberColumn("EV/Rev", format="%.2f x"),
                "Filing Date": st.column_config.TextColumn("Date Filed"),
                "FY": st.column_config.TextColumn("FY")
            },
            hide_index=True,
            use_container_width=True
        )
        
        st.markdown("---")
        

        
        # --- Visualizations ---
        st.markdown("### 📊 Comparative Analysis")
        
        viz_tabs = st.tabs(["📈 Revenue Comparison", "💰 Profitability", "💵 Valuation Multiples", "📊 Efficiency & Risk", "🎯 Growth vs Value", "📋 Full Data Table"])
        
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
            # Efficiency & Risk: ROIC, Interest Coverage, Rule of 40
            st.markdown("#### Efficiency & Risk")
            eff_cols = ["ticker", "roic_%", "interest_coverage", "revenue_growth_%", "rule_of_40", "rule_of_40_status"]
            eff_available = [c for c in eff_cols if c in df.columns]
            if eff_available:
                eff_df = df[eff_available].copy()
                eff_df["roic_%"] = eff_df["roic_%"].apply(lambda x: f"{x:.1f}%" if x is not None and pd.notna(x) else "—")
                eff_df["interest_coverage"] = eff_df["interest_coverage"].apply(lambda x: f"{x:.1f}x" if x is not None and pd.notna(x) and x != 0 else "—")
                eff_df["revenue_growth_%"] = eff_df["revenue_growth_%"].apply(lambda x: f"{x:.1f}%" if x is not None and pd.notna(x) else "—")
                eff_df["rule_of_40"] = eff_df["rule_of_40"].apply(lambda x: f"{x:.1f}" if x is not None and pd.notna(x) else "—")
                eff_df.columns = ["Ticker", "ROIC %", "Interest Coverage", "Revenue Growth %", "Rule of 40", "Rule of 40 Status"]
                st.dataframe(eff_df, use_container_width=True, hide_index=True)
                st.caption("ROIC = NOPAT / Invested Capital. Interest Coverage = Operating Income / Interest Expense. Rule of 40 = Revenue Growth % + Net Margin % (Pass if ≥ 40).")
                # Highlight Rule of 40 status
                if "rule_of_40_status" in df.columns:
                    st.markdown("**Rule of 40 status**")
                    for _, row in df.iterrows():
                        status = row.get("rule_of_40_status") or "—"
                        score = row.get("rule_of_40")
                        color = "green" if status == "Pass" else "red" if status == "Fail" else "gray"
                        score_str = f" ({score:.1f})" if score is not None and pd.notna(score) else ""
                        st.markdown(f"- **{row['ticker']}**: <span style='color:{color}'>{status}</span>{score_str}", unsafe_allow_html=True)
            else:
                st.info("Efficiency & Risk metrics will appear after the next run (advanced extraction).")
        
        with viz_tabs[4]:
            # **New Feature: Valuation vs Growth Scatter Plot**
            st.markdown("#### Growth vs Valuation (Rule of 40 vs EV/Revenue)")
            scatter_cols = ["ticker", "rule_of_40", "EV/Revenue", "net_margin_%"]
            if all(c in df.columns for c in scatter_cols) and not df[scatter_cols].empty:
                plot_df_s = df[scatter_cols].copy()
                plot_df_s["EV/Revenue"] = plot_df_s["EV/Revenue"].replace([float("inf"), float("-inf")], 0).fillna(0)
                plot_df_s["rule_of_40"] = plot_df_s["rule_of_40"].fillna(0)
                # Keep reasonable domains
                plot_df_s = plot_df_s[(plot_df_s["EV/Revenue"] > 0) & (plot_df_s["EV/Revenue"] < 100)]
                
                if not plot_df_s.empty:
                    fig_scatter = px.scatter(
                        plot_df_s,
                        x="rule_of_40",
                        y="EV/Revenue",
                        text="ticker",
                        size="net_margin_%",
                        color="EV/Revenue",
                        color_continuous_scale="Viridis",
                        title="Is the Valuation Justified by the Rule of 40?",
                        labels={"rule_of_40": "Rule of 40 Score (Growth + Margin)", "EV/Revenue": "EV / Revenue Multiple"}
                    )
                    fig_scatter.update_traces(textposition='top center')
                    # Add reference line for Rule of 40 threshold
                    fig_scatter.add_vline(x=40, line_dash="dash", line_color="red", annotation_text="Rule of 40 Threshold")
                    fig_scatter.update_layout(height=500)
                    st.plotly_chart(fig_scatter, use_container_width=True)
                else:
                    st.info("Outlier values prevented scatter plot rendering.")
            else:
                st.info("Scatter plot requires valid EV/Revenue and Rule of 40 data.")

        
        with viz_tabs[5]:
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
            
            cols = ["ticker", "filing_date"]
            if "fiscal_year" in display_df.columns:
                display_df["fiscal_year_fmt"] = display_df["fiscal_year"].apply(lambda x: f"FY{x}" if x else "—")
                cols.append("fiscal_year_fmt")
            cols += ["revenue_fmt", "net_income_fmt", "ebitda_fmt", "net_margin_%_fmt", "mkt_cap_fmt", "P/E_Ratio_fmt", "EV/Revenue_fmt", "EV/EBITDA_fmt"]
            out = display_df[[c for c in cols if c in display_df.columns]].copy()
            col_names = ["Ticker", "Filing Date"] + (["Fiscal Year"] if "fiscal_year_fmt" in out.columns else []) + ["Revenue (USD Millions)", "Net Income (USD Millions)", "EBITDA (USD Millions)", "Net Margin %", "Market Cap", "P/E", "EV/Revenue", "EV/EBITDA"]
            out.columns = col_names
            st.dataframe(out, use_container_width=True, hide_index=True)
        
        st.markdown("---")
        
        # --- AI Executive Summary Generation ---
        st.markdown("### 🤖 Wall Street AI Executive Summary")
        st.caption("Generate a professional Investment Banking briefing instantly analyzing the Comps table above.")
        
        if st.button("Generate Executive Briefing", icon="✨", type="secondary"):
            with st.spinner("Synthesizing metrics using Gemini..."):
                import time
                client = genai.Client(api_key=api_key)
                df_string = out.to_string()
                
                prompt = f"""
                You are an elite Wall Street Investment Banker. Review this precise comparable company analysis (Comps) table:
                {df_string}
                
                Write a punchy, 3-paragraph executive summary covering:
                1. The clear sector leader based on size and profitability.
                2. Valuation discrepancies: Who trades at a premium vs discount (P/E and EV/Rev)? Is the premium justified by their Rule of 40 efficiency?
                3. Key risks or laggards identified in the cohort.
                
                Do not hallucinate. Do not mention standard disclaimers. Use bolding to emphasize ticker symbols and key metrics. Keep it incredibly professional.
                """
                
                max_retries = 3
                success = False
                
                for attempt in range(max_retries):
                    try:
                        response = client.models.generate_content(
                            model="gemini-2.0-flash",
                            contents=prompt
                        )
                        st.info(response.text)
                        success = True
                        break
                    except Exception as e:
                        err_msg = str(e).lower()
                        if "429" in err_msg or "too many requests" in err_msg or "resourceexhausted" in err_msg:
                            if attempt < max_retries - 1:
                                wait_time = 15 * (2 ** attempt)  # 15s, 30s
                                st.warning(f"⚠️ API Rate Limit reached (Free Tier). Retrying in {wait_time}s...")
                                time.sleep(wait_time)
                            else:
                                st.error(f"❌ Failed to generate AI summary after {max_retries} attempts: {str(e)}")
                        else:
                            st.error(f"⚠️ Failed to generate AI summary: {str(e)}")
                            break
                
                if not success and attempt == max_retries - 1:
                    st.info("Try waiting a minute before generating the summary to let the Gemini Free Tier quota reset.")
                    
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