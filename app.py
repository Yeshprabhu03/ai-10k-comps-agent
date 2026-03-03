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
        background-color: #0e1117;
        color: #f0f2f6;
    }
    
    /* Header Typography */
    .main-header {
        font-size: 3.5rem;
        font-weight: 800;
        background: linear-gradient(135deg, #00c6ff, #0072ff);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
        letter-spacing: -1px;
    }
    .sub-header {
        color: #8b949e;
        font-size: 1.2rem;
        font-weight: 400;
        margin-bottom: 2.5rem;
    }
    
    /* Glowing Glassmorphism Metric Cards */
    div[data-testid="metric-container"] {
        background: rgba(26, 28, 36, 0.7);
        border: 1px solid rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 1.5rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
    }
    div[data-testid="metric-container"]:hover {
        transform: translateY(-5px);
        box-shadow: 0 8px 15px rgba(0, 198, 255, 0.2);
        border-color: rgba(0, 198, 255, 0.5);
    }
    
    /* Sleek Primary Buttons */
    .stButton>button[kind="primary"] {
        width: 100%;
        background: linear-gradient(135deg, #0072ff, #00c6ff);
        color: white;
        font-weight: 700;
        letter-spacing: 0.5px;
        padding: 0.8rem;
        border-radius: 8px;
        border: none;
        box-shadow: 0 4px 10px rgba(0, 114, 255, 0.4);
        transition: all 0.3s ease;
    }
    .stButton>button[kind="primary"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 15px rgba(0, 114, 255, 0.6);
        background: linear-gradient(135deg, #00c6ff, #0072ff);
    }
    
    /* Secondary Buttons */
    .stButton>button[kind="secondary"] {
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.2);
        background: rgba(255, 255, 255, 0.05);
        transition: all 0.2s ease;
    }
    .stButton>button[kind="secondary"]:hover {
        background: rgba(255, 255, 255, 0.1);
        border-color: rgba(255, 255, 255, 0.4);
    }
    </style>
""", unsafe_allow_html=True)

# --- SEC Ticker Loader (cached for 8,000+ U.S. companies) ---
@st.cache_data(ttl=3600)
def _load_sec_tickers():
    return get_all_sec_tickers()


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

# --- Sidebar: Settings ---
if "peer_list" not in st.session_state:
    st.session_state.peer_list = []

with st.sidebar:
    st.markdown("### ⚙️ Analysis Settings")
    st.markdown("---")
    
    # 1. Primary company: searchable SEC dropdown (entire U.S. market)
    selected_ticker = st_searchbox(
        search_tickers_sec,
        key="ticker_search",
        label="🔍 Search Company (SEC list)",
        placeholder="Type 'Apple' or 'AAPL'... (8,000+ companies)",
        default=None
    )
    
    manual_ticker = st.text_input(
        "📝 Or enter ticker",
        value="",
        placeholder="e.g., AAPL, MSFT",
        help="Type ticker directly"
    ).upper().strip()
    
    target_ticker = selected_ticker or manual_ticker

    if target_ticker:
        try:
            ticker_obj = yf.Ticker(target_ticker)
            info = ticker_obj.info
            
            st.markdown("---")
            st.markdown("### 📋 Company Info")
            company_name = info.get("longName", target_ticker)
            industry = info.get("industry", "N/A")
            sector = info.get("sector", "N/A")
            st.markdown(f"**{company_name}**")
            st.caption(f"Ticker: **{target_ticker}**")
            col1, col2 = st.columns(2)
            with col1:
                st.metric("Industry", industry[:20] + "..." if len(industry) > 20 else industry)
            with col2:
                st.metric("Sector", sector[:15] + "..." if len(sector) > 15 else sector)
            
            # Peer selection: searchable SEC dropdown, add to list
            st.markdown("---")
            st.markdown("### 👥 Peer Selection (SEC list)")
            st.caption("Type a company name or ticker below — suggestions appear as you type.")
            _load_sec_tickers()  # Preload so peer search has data ready
            add_peer = st_searchbox(
                search_tickers_sec,
                key="peer_search",
                label="Search to add peer company",
                placeholder="e.g. Microsoft, GOOGL, Amazon...",
                default=None
            )
            if add_peer and add_peer not in st.session_state.peer_list:
                st.session_state.peer_list = list(st.session_state.peer_list) + [add_peer]
            if st.session_state.peer_list:
                for i, p in enumerate(st.session_state.peer_list):
                    c1, c2 = st.columns([3, 1])
                    with c1:
                        st.caption(f"**{p}**")
                    with c2:
                        if st.button("Remove", key=f"rm_{p}_{i}"):
                            st.session_state.peer_list = [x for x in st.session_state.peer_list if x != p]
                            st.rerun()
                if st.button("Clear all peers"):
                    st.session_state.peer_list = []
                    st.rerun()
            peers = list(st.session_state.peer_list)
            if not peers:
                st.warning("⚠️ Add at least one peer above")
            
            st.markdown("---")
            run_button = st.button("🚀 Generate Comps Analysis", use_container_width=True, type="primary")
            
        except Exception as e:
            st.error(f"❌ Error: {str(e)}")
            st.info("Check the ticker symbol and try again.")
            run_button = False
    else:
        st.info("👆 Search for a company (SEC list) or enter a ticker to begin.")
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
    
    # 1. Fetch SEC Data (skips tickers with no 10-K/20-F gracefully)
    with st.spinner("Extracting 10-K data..."):
        try:
            df = fetch_and_analyze(all_tickers)
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
                
                mkt_cap = f_info.get("market_cap", 0)
                
                # Check for currency mismatch and convert mkt_cap to USD
                quote_currency = f_info.get("currency", "USD")
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
                fy = row.get("fiscal_year", "")
                st.caption(f"Filed: {row['filing_date']}" + (f"  ·  FY{fy}" if fy else ""))
        
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