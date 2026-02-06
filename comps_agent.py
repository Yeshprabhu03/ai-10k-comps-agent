import os
import json
import re
import time
import pandas as pd
from dotenv import load_dotenv
from google import genai
from edgar import *

# 1. Setup
load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
set_identity("Yeshwanth your-email@fordham.edu")


def _extract_year_from_text(text):
    """Find 4-digit year (1990-2030) in a string; return the max if multiple."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    s = str(text)
    years = [int(m) for m in re.findall(r"\b(19[0-9]\d|20[0-3]\d)\b", s)]
    return max(years) if years else None


def _get_latest_column_data(f_obj, filing_date, ticker):
    """
    Try to get income statement as DataFrame, find the column with the latest fiscal year,
    return a dict of {revenue, net_income, operating_income, dep_amort} in millions and fiscal_year,
    or None if we should fall back to LLM.
    """
    try:
        income_stmt = f_obj.financials.income_statement()
        df = income_stmt.to_dataframe(include_dimensions=False)
    except Exception:
        try:
            income_stmt = f_obj.financials.statements_of_operations()
            df = income_stmt.to_dataframe(include_dimensions=False)
        except Exception:
            return None
    if df is None or df.empty:
        return None
    # Columns might be periods, dates, or strings; find year for each
    col_years = {}
    for i, col in enumerate(df.columns):
        y = None
        if hasattr(col, "year"):
            y = getattr(col, "year", None)
        if y is None and hasattr(col, "end_date"):
            end = getattr(col, "end_date", None)
            if end is not None:
                y = getattr(end, "year", None) or (int(str(end)[:4]) if str(end) else None)
        if y is None:
            y = _extract_year_from_text(col)
        if y is not None:
            col_years[i] = y
    if not col_years:
        return None
    latest_year = max(col_years.values())
    best_col_idx = max((i for i, y in col_years.items() if y == latest_year), key=lambda i: i)
    col_series = df.iloc[:, best_col_idx]
    # Map common row labels to our keys (edgartools uses standardized concepts)
    def find_value(*names):
        for idx in df.index:
            idx_str = str(idx).lower()
            for n in names:
                if n.lower() in idx_str:
                    val = col_series.get(idx)
                    if val is not None and not (isinstance(val, float) and pd.isna(val)):
                        try:
                            return float(val)
                        except (TypeError, ValueError):
                            pass
        return 0.0
    revenue = find_value("revenue", "sales", "net sales", "total net sales", "revenues")
    net_inc = find_value("net income", "net earnings", "profit")
    op_inc = find_value("operating income", "income from operations", "operating profit")
    da = find_value("depreciation", "amortization", "depreciation and amortization", "d&a")
    if revenue == 0 and net_inc == 0 and op_inc == 0:
        return None
    return {
        "revenue": revenue,
        "net_income": net_inc,
        "operating_income": op_inc,
        "dep_amort": da,
        "reporting_currency": "USD",
        "fiscal_year": latest_year,
    }


def fetch_and_analyze(tickers):
    results = []
    for ticker in tickers:
        for attempt in range(2):
            try:
                print(f"🚀 Processing {ticker}...", flush=True)
                company = Company(ticker)
                
                # Support 10-K (US) and 20-F (Foreign) filings
                filing = company.get_filings(form=["10-K", "20-F"]).latest()
                if not filing:
                    print(f"⚠️ No filing found for {ticker}")
                    break
                
                filing_date = filing.filing_date
                f_obj = filing.obj()

                # Path 1: Programmatic — get DataFrame, pick column with latest year by parsing column years
                data = _get_latest_column_data(f_obj, filing_date, ticker)

                if data is None:
                    # Path 2: Two-step LLM — step 1: identify latest-year column; step 2: extract only from that column
                    try:
                        income_stmt = f_obj.financials.income_statement()
                        financial_summary = str(income_stmt)
                    except Exception:
                        try:
                            income_stmt = f_obj.financials.statements_of_operations()
                            financial_summary = str(income_stmt)
                        except Exception:
                            financial_summary = str(f_obj.financials)
                    try:
                        fd_str = str(filing_date)
                        filing_yr = int(fd_str[:4]) if fd_str else None
                    except Exception:
                        filing_yr = getattr(filing_date, "year", None)
                    latest_fy = (filing_yr - 1) if filing_yr else 2025

                    try:
                        # Step 1: Get each column's header and year
                        step1_prompt = (
                            "Below is a financial table with multiple YEAR columns. List each DATA column and the fiscal year that column represents.\n"
                            "Return ONLY this JSON, no other text:\n"
                            '{"columns": [{"header": "exact column header text", "year": 2025}, ...]}\n'
                            "Get the year from the header (e.g. 'Year ended December 31, 2025' -> 2025). Include every data column.\n\n"
                            f"Data for {ticker}:\n{financial_summary}"
                        )
                        r1 = client.models.generate_content(model="gemini-2.0-flash", contents=step1_prompt)
                        raw1 = r1.text.strip().replace("```json", "").replace("```", "")
                        step1 = json.loads(raw1)
                        cols = step1.get("columns") or []
                        if not cols:
                            raise ValueError("No columns identified")
                        latest_col = max(cols, key=lambda c: int(c.get("year") or 0))
                        latest_header = (latest_col.get("header") or "").strip()
                        latest_fy = int(latest_col.get("year") or latest_fy)

                        # Step 2: Extract ONLY from the column with this exact header
                        step2_prompt = (
                            f"Extract numbers ONLY from the column whose header is EXACTLY: \"{latest_header}\"\n"
                            "Ignore the first column. Ignore all other columns. Use only that column.\n"
                            "Line items: Revenue (or Total net sales), Net income, Operating income, Depreciation and amortization. "
                            "Values in MILLIONS. Return ONLY valid JSON, no markdown. "
                            "Keys: revenue, net_income, operating_income, dep_amort, reporting_currency, fiscal_year. "
                            f"Set fiscal_year to {latest_fy}.\n\n"
                            f"Data for {ticker}:\n{financial_summary}"
                        )
                        r2 = client.models.generate_content(model="gemini-2.0-flash", contents=step2_prompt)
                        raw2 = r2.text.strip().replace("```json", "").replace("```", "")
                        data = json.loads(raw2)
                    except Exception:
                        # Fallback: single-call extraction
                        fallback_prompt = (
                            "From the table below, use ONLY the column for the MOST RECENT year (e.g. 2025 or 2024). "
                            "Do NOT use the 2023 column. Identify the column by its header year, not by position. "
                            "Extract: revenue, net_income, operating_income, dep_amort. Values in MILLIONS. "
                            "Return ONLY JSON: revenue, net_income, operating_income, dep_amort, reporting_currency, fiscal_year.\n\n"
                            f"Data for {ticker}:\n{financial_summary}"
                        )
                        r = client.models.generate_content(model="gemini-2.0-flash", contents=fallback_prompt)
                        raw = r.text.strip().replace("```json", "").replace("```", "")
                        data = json.loads(raw)
                
                # Values stay in MILLIONS (raw float from prompt)
                def clean_num(key):
                    val = data.get(key, 0)
                    if val is None or str(val).lower() == 'none': 
                        return 0.0
                    return float(str(val).replace(',', '').replace('$', '').replace(' ', ''))

                revenue = clean_num('revenue')
                net_inc = clean_num('net_income')
                op_inc = clean_num('operating_income')
                da = clean_num('dep_amort')
                
                # Normalize to millions: model sometimes returns dollars (e.g. 96773000000)
                # If value looks like dollars (> 1e8), convert to millions by / 1e6
                def to_millions(val):
                    if val is None or val == 0:
                        return 0.0
                    return val / 1e6 if abs(val) > 1e8 else val
                revenue = to_millions(revenue)
                net_inc = to_millions(net_inc)
                op_inc = to_millions(op_inc)
                da = to_millions(da)
                
                reporting_currency = (data.get('reporting_currency') or 'USD').strip().upper()[:3]
                
                # Convert to USD millions if filing is in another currency (e.g. SONY in JPY)
                fx_to_usd = 1.0
                if reporting_currency != 'USD':
                    try:
                        import yfinance as yf
                        # USD per 1 unit of reporting currency (e.g. USD per 1 JPY)
                        if reporting_currency == 'JPY':
                            # USDJPY=X = JPY per 1 USD -> USD per 1 JPY = 1/Close
                            t = yf.Ticker("USDJPY=X")
                            hist = t.history(period="5d")
                            if not hist.empty:
                                fx_to_usd = 1.0 / float(hist["Close"].iloc[-1])
                            else:
                                fx_to_usd = 0.0067
                        elif reporting_currency == 'EUR':
                            # EURUSD=X = USD per 1 EUR
                            t = yf.Ticker("EURUSD=X")
                            hist = t.history(period="5d")
                            if not hist.empty:
                                fx_to_usd = float(hist["Close"].iloc[-1])
                            else:
                                fx_to_usd = 1.08
                        else:
                            # Generic: XXXUSD=X try USD per 1 XXX
                            t = yf.Ticker(f"{reporting_currency}USD=X")
                            hist = t.history(period="5d")
                            if not hist.empty:
                                fx_to_usd = float(hist["Close"].iloc[-1])
                    except Exception:
                        fx_to_usd = 1.0
                
                revenue_usd = revenue * fx_to_usd
                net_inc_usd = net_inc * fx_to_usd
                ebitda_usd = (op_inc + da) * fx_to_usd
                
                fiscal_year = data.get("fiscal_year")
                if isinstance(fiscal_year, (int, float)):
                    fiscal_year = int(fiscal_year)
                else:
                    fiscal_year = int(fiscal_year) if fiscal_year else 2025

                results.append({
                    "ticker": ticker,
                    "filing_date": filing_date,
                    "fiscal_year": fiscal_year,
                    "revenue": revenue_usd,
                    "net_income": net_inc_usd,
                    "ebitda": ebitda_usd,
                    "net_margin_%": (net_inc_usd / revenue_usd * 100) if revenue_usd > 0 else 0,
                })
                print(f"✅ Successfully analyzed {ticker}", flush=True)
                break 
                
            except Exception as e:
                if "429" in str(e):
                    print(f"⚠️ Rate limit. Waiting 20s...", flush=True)
                    time.sleep(20)
                else:
                    print(f"❌ Error with {ticker}: {e}", flush=True)
                    break
        
        # Inter-ticker delay to preserve API quota
        if ticker != tickers[-1]:
            time.sleep(10)

    return pd.DataFrame(results)

if __name__ == "__main__":
    # Test block to verify scaling
    df = fetch_and_analyze(["AAPL"])
    print(df)