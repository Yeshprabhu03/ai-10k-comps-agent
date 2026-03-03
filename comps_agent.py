import os
import json
import re
import time
import pandas as pd
from urllib.request import Request, urlopen
from dotenv import load_dotenv
from google import genai
from edgar import *

# 1. Setup
load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
set_identity("Yeshwanth your-email@fordham.edu")

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"


def get_all_sec_tickers():
    """
    Fetch the official SEC company tickers mapping and return a list of (ticker, company_name).
    Used to support searchable dropdown over the entire U.S. stock market.
    """
    try:
        req = Request(
            SEC_TICKERS_URL,
            headers={"User-Agent": "IB-Comps-Agent/1.0 (https://github.com/your-repo; contact@example.com)"}
        )
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        # Format: {"0": {"cik_str": ..., "ticker": "AAPL", "title": "Apple Inc."}, ...}
        out = []
        seen = set()
        for key in sorted(data.keys(), key=lambda k: int(k) if k.isdigit() else 0):
            entry = data.get(key) or {}
            ticker = (entry.get("ticker") or "").strip().upper()
            title = (entry.get("title") or "").strip()
            if ticker and ticker not in seen:
                seen.add(ticker)
                out.append((ticker, title or ticker))
        return out
    except Exception as e:
        print(f"⚠️ Could not fetch SEC tickers: {e}", flush=True)
        return []


def _extract_year_from_text(text):
    """Find 4-digit year (1990-2030) in a string; return the max if multiple."""
    if text is None or (isinstance(text, float) and pd.isna(text)):
        return None
    s = str(text)
    years = [int(m) for m in re.findall(r"\b(19[0-9]\d|20[0-3]\d)\b", s)]
    return max(years) if years else None


def _calc_roic(operating_income, tax_provision, net_income, total_assets, current_liabilities):
    """ROIC = NOPAT / Invested Capital; NOPAT = Operating Income * (1 - Tax Rate); Invested Capital = Total Assets - Current Liabilities."""
    if not total_assets or not current_liabilities or (total_assets - current_liabilities) <= 0:
        return None
    pretax = net_income + tax_provision if (net_income + tax_provision) else 1
    tax_rate = tax_provision / pretax if pretax and pretax > 0 else 0
    tax_rate = max(0, min(1, tax_rate))
    nopat = operating_income * (1 - tax_rate) if operating_income else 0
    invested_capital = total_assets - current_liabilities
    return (nopat / invested_capital * 100) if invested_capital and nopat else None


def _calc_interest_coverage(operating_income, interest_expense):
    """Interest Coverage = Operating Income / Interest Expense."""
    if interest_expense is None or interest_expense <= 0:
        return None
    if operating_income is None or operating_income < 0:
        return 0.0
    return operating_income / interest_expense


def _calc_rule_of_40(revenue_growth_pct, net_margin_pct):
    """Rule of 40 = Revenue Growth % + Net Margin %. Pass if >= 40."""
    if revenue_growth_pct is None and net_margin_pct is None:
        return None, None
    growth = revenue_growth_pct if revenue_growth_pct is not None else 0
    margin = net_margin_pct if net_margin_pct is not None else 0
    score = growth + margin
    return round(score, 2), "Pass" if score >= 40 else "Fail"


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
    def find_value(names_exact, names_regex, exclude_regex=None):
        """
        Tier 1: Try exact matches on index (e.g., 'net sales').
        Tier 2: Try word boundary \b matches using regex, excluding terms like 'unearned' or 'returns'.
        """
        # Tier 1: Exact matches
        for idx in df.index:
            idx_str = str(idx).lower().strip()
            if idx_str in [n.lower() for n in names_exact]:
                val = col_series.get(idx)
                if val is not None and not (isinstance(val, float) and pd.isna(val)):
                    try: return float(val)
                    except (TypeError, ValueError): pass
        
        # Tier 2: Regex word-boundary matches
        import re
        for idx in df.index:
            idx_str = str(idx).lower().strip()
            if exclude_regex and re.search(exclude_regex, idx_str):
                continue
            for pattern in names_regex:
                if re.search(pattern, idx_str):
                    val = col_series.get(idx)
                    if val is not None and not (isinstance(val, float) and pd.isna(val)):
                        try: return float(val)
                        except (TypeError, ValueError): pass
        return 0.0

    # Strict definitions using regex boundaries to prevent matching "sales returns" when searching for "sales"
    revenue = find_value(
        names_exact=["revenue", "revenues", "net revenue", "net revenues", "sales", "net sales", "total net sales"],
        names_regex=[r"\b(?:net )?sales\b", r"\b(?:net )?revenue(?:s)?\b"],
        exclude_regex=r"unearned|deferred|returns|allowances|cost of|related party"
    )
    net_inc = find_value(
        names_exact=["net income", "net earnings"],
        names_regex=[r"\bnet income\b", r"\bnet earnings\b"],
        exclude_regex=r"noncontrolling|attributable to|comprehensive"
    )
    op_inc = find_value(
        names_exact=["operating income", "income from operations", "operating profit"],
        names_regex=[r"\boperating income\b", r"\bincome from operations\b", r"\boperating profit\b"],
        exclude_regex=r"non-operating|nonoperating"
    )
    da = find_value(
        names_exact=["depreciation", "amortization", "depreciation and amortization", "d&a"],
        names_regex=[r"\bdepreciation\b", r"\bamortization\b"],
        exclude_regex=r"accumulated|software|property|equipment"
    )
    interest_exp = find_value(
        names_exact=["interest expense", "interest expense net", "interest"],
        names_regex=[r"\binterest expense\b"],
        exclude_regex=r"income|revenue|capitalized"
    )
    tax_prov = find_value(
        names_exact=["tax provision", "income tax", "provision for income tax", "income tax expense"],
        names_regex=[r"\bprovision for (?:income )?taxes\b", r"\b(?:income )?tax expense\b"],
        exclude_regex=r"benefit|deferred|receivable|payable"
    )

    # Prior-year revenue from second-latest column if available
    prior_rev = 0.0
    prev_year_cols = [i for i, y in col_years.items() if y < latest_year]
    if prev_year_cols:
        prev_col_idx = max(prev_year_cols, key=lambda i: col_years[i])
        prev_series = df.iloc[:, prev_col_idx]
        for idx in df.index:
            idx_str = str(idx).lower().strip()
            import re
            if not re.search(r"unearned|deferred|returns|allowances|cost of", idx_str):
                if idx_str in ["revenue", "revenues", "net revenue", "sales", "net sales"] or re.search(r"\b(?:net )?sales\b", idx_str) or re.search(r"\b(?:net )?revenue(?:s)?\b", idx_str):
                    try:
                        prior_rev = float(prev_series.get(idx, 0) or 0)
                        break
                    except (TypeError, ValueError):
                        pass

    if revenue == 0 and net_inc == 0 and op_inc == 0:
        return None

    out = {
        "revenue": revenue,
        "net_income": net_inc,
        "operating_income": op_inc,
        "dep_amort": da,
        "interest_expense": interest_exp,
        "tax_provision": tax_prov,
        "prior_year_revenue": prior_rev,
        "reporting_currency": "USD",
        "fiscal_year": latest_year,
        "source": "SEC XBRL (Exact)",
        "confidence": "High"
    }
    # Balance sheet: try to get total_assets, total_liabilities, current_liabilities
    try:
        bs = f_obj.financials.balance_sheet()
        bs_df = bs.to_dataframe(include_dimensions=False)
        if bs_df is not None and not bs_df.empty:
            bs_col_years = {}
            for i, col in enumerate(bs_df.columns):
                y = _extract_year_from_text(col) or (getattr(col, "year", None) if hasattr(col, "year") else None)
                if y is not None:
                    bs_col_years[i] = y
            if bs_col_years and latest_year in bs_col_years.values():
                bs_best = max((i for i, y in bs_col_years.items() if y == latest_year), key=lambda i: i)
                bs_series = bs_df.iloc[:, bs_best]
                def bs_find(names_exact, names_regex, exclude_regex=None):
                    for idx in bs_df.index:
                        idx_str = str(idx).lower().strip()
                        if idx_str in [n.lower() for n in names_exact]:
                            try: return float(bs_series.get(idx, 0) or 0)
                            except (TypeError, ValueError): pass
                    
                    import re
                    for idx in bs_df.index:
                        idx_str = str(idx).lower().strip()
                        if exclude_regex and re.search(exclude_regex, idx_str):
                            continue
                        for pattern in names_regex:
                            if re.search(pattern, idx_str):
                                try: return float(bs_series.get(idx, 0) or 0)
                                except (TypeError, ValueError): pass
                    return 0.0

                out["total_assets"] = bs_find(
                    names_exact=["total assets", "assets"],
                    names_regex=[r"\btotal assets\b", r"^assets$"],
                    exclude_regex=r"current|noncurrent|non-current|operating|intangible|tax"
                )
                out["total_liabilities"] = bs_find(
                    names_exact=["total liabilities", "liabilities"],
                    names_regex=[r"\btotal liabilities\b", r"^liabilities$"],
                    exclude_regex=r"current|noncurrent|non-current|operating|tax|lease"
                )
                out["current_liabilities"] = bs_find(
                    names_exact=["current liabilities", "total current liabilities"],
                    names_regex=[r"\bcurrent liabilities\b"],
                    exclude_regex=r"noncurrent|non-current"
                )
    except Exception:
        out["total_assets"] = 0.0
        out["total_liabilities"] = 0.0
        out["current_liabilities"] = 0.0
    return out


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
                    print(f"⚠️ No filing found for {ticker} (skipped gracefully)", flush=True)
                    break  # Skip tickers with no 10-K/20-F (e.g. new IPOs)
                
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

                        # Step 2: Extract ONLY from the column with this exact header (incl. advanced metrics fields)
                        step2_prompt = (
                            f"Extract numbers ONLY from the column whose header is EXACTLY: \"{latest_header}\"\n"
                            "Ignore the first column. Ignore all other columns. Use only that column.\n"
                            "From the INCOME STATEMENT: revenue, net_income, operating_income, dep_amort, interest_expense, tax_provision. "
                            "Also from the SAME filing, from BALANCE SHEET (same fiscal year): total_assets, total_liabilities, current_liabilities. "
                            "From the PRIOR YEAR column (previous year) in the income statement: prior_year_revenue. "
                            "All values in MILLIONS. Return ONLY valid JSON, no markdown. "
                            "Keys: revenue, net_income, operating_income, dep_amort, interest_expense, tax_provision, "
                            "total_assets, total_liabilities, current_liabilities, prior_year_revenue, reporting_currency, fiscal_year. "
                            f"Set fiscal_year to {latest_fy}. Use 0 for any missing value.\n\n"
                            f"Data for {ticker}:\n{financial_summary}"
                        )
                        r2 = client.models.generate_content(model="gemini-2.0-flash", contents=step2_prompt)
                        raw2 = r2.text.strip().replace("```json", "").replace("```", "")
                        data = json.loads(raw2)
                    except Exception:
                        # Fallback: single-call extraction
                        fallback_prompt = (
                            "From the table below, use ONLY the column for the MOST RECENT year. Do NOT use 2023. "
                            "Extract: revenue, net_income, operating_income, dep_amort, interest_expense, tax_provision, "
                            "total_assets, total_liabilities, current_liabilities, prior_year_revenue (from prior year column). "
                            "Values in MILLIONS. Use 0 if missing. Return ONLY JSON with those keys plus reporting_currency, fiscal_year.\n\n"
                            f"Data for {ticker}:\n{financial_summary}"
                        )
                        r = client.models.generate_content(model="gemini-2.0-flash", contents=fallback_prompt)
                        raw = r.text.strip().replace("```json", "").replace("```", "")
                        data = json.loads(raw)
                    
                    data["source"] = "LLM Fallback"
                    data["confidence"] = "Medium"
                
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
                interest_exp = clean_num('interest_expense')
                tax_prov = clean_num('tax_provision')
                total_assets = clean_num('total_assets')
                total_liab = clean_num('total_liabilities')
                current_liab = clean_num('current_liabilities')
                prior_rev = clean_num('prior_year_revenue')
                
                # Determine magnitude strictly on the Revenue value. 
                # If Revenue > $10,000, we conservatively assume values are in raw dollars, requiring division by 1,000,000.
                scale_factor = 1.0
                if data.get("source") != "LLM Fallback" and revenue > 10000:
                    scale_factor = 1_000_000.0
                
                revenue = revenue / scale_factor
                net_inc = net_inc / scale_factor
                op_inc = op_inc / scale_factor
                da = da / scale_factor
                interest_exp = interest_exp / scale_factor
                tax_prov = tax_prov / scale_factor
                total_assets = total_assets / scale_factor
                total_liab = total_liab / scale_factor
                current_liab = current_liab / scale_factor
                prior_rev = prior_rev / scale_factor
                
                reporting_currency = (data.get('reporting_currency') or 'USD').strip().upper()[:3]
                
                # Convert to USD millions if filing is in another currency (e.g. SONY in JPY)
                fx_to_usd = 1.0
                fx_source = "USD (Native)"
                
                # Safe static fallbacks in case yfinance API is down
                static_fx = {
                    "JPY": 0.0067,
                    "EUR": 1.08,
                    "GBP": 1.25,
                    "CAD": 0.74,
                    "CHF": 1.13,
                    "AUD": 0.65
                }

                if reporting_currency != 'USD':
                    try:
                        import yfinance as yf
                        if reporting_currency == 'JPY':
                            t = yf.Ticker("USDJPY=X")
                            hist = t.history(period="5d")
                            fx_to_usd = 1.0 / float(hist["Close"].iloc[-1])
                            fx_source = "Live (yfinance)"
                        elif reporting_currency == 'EUR':
                            t = yf.Ticker("EURUSD=X")
                            hist = t.history(period="5d")
                            fx_to_usd = float(hist["Close"].iloc[-1])
                            fx_source = "Live (yfinance)"
                        else:
                            t = yf.Ticker(f"{reporting_currency}USD=X")
                            hist = t.history(period="5d")
                            fx_to_usd = float(hist["Close"].iloc[-1])
                            fx_source = "Live (yfinance)"
                    except Exception as e:
                        print(f"⚠️ Live FX lookup failed for {reporting_currency}: {e}. Using static fallback.", flush=True)
                        fx_to_usd = static_fx.get(reporting_currency, 1.0)
                        fx_source = f"Static Fallback (Rate: {fx_to_usd})"
                
                revenue_usd = revenue * fx_to_usd
                net_inc_usd = net_inc * fx_to_usd
                ebitda_usd = (op_inc + da) * fx_to_usd
                total_assets_usd = total_assets * fx_to_usd
                total_liab_usd = total_liab * fx_to_usd
                current_liab_usd = current_liab * fx_to_usd
                prior_rev_usd = prior_rev * fx_to_usd
                op_inc_usd = op_inc * fx_to_usd
                tax_prov_usd = tax_prov * fx_to_usd
                interest_exp_usd = interest_exp * fx_to_usd
                
                fiscal_year = data.get("fiscal_year")
                if isinstance(fiscal_year, (int, float)):
                    fiscal_year = int(fiscal_year)
                else:
                    fiscal_year = int(fiscal_year) if fiscal_year else 2025

                net_margin_pct = (net_inc_usd / revenue_usd * 100) if revenue_usd > 0 else 0
                revenue_growth_pct = ((revenue_usd - prior_rev_usd) / prior_rev_usd * 100) if prior_rev_usd and prior_rev_usd > 0 else None
                roic = _calc_roic(op_inc_usd, tax_prov_usd, net_inc_usd, total_assets_usd, current_liab_usd)
                interest_coverage = _calc_interest_coverage(op_inc_usd, interest_exp_usd)
                rule_of_40_score, rule_of_40_status = _calc_rule_of_40(revenue_growth_pct, net_margin_pct)

                results.append({
                    "ticker": ticker,
                    "filing_date": filing_date,
                    "fiscal_year": fiscal_year,
                    "revenue": revenue_usd,
                    "net_income": net_inc_usd,
                    "ebitda": ebitda_usd,
                    "net_margin_%": net_margin_pct,
                    "revenue_growth_%": revenue_growth_pct,
                    "roic_%": roic,
                    "interest_coverage": interest_coverage,
                    "rule_of_40": rule_of_40_score,
                    "rule_of_40_status": rule_of_40_status or "—",
                    "data_source": data.get("source", "Unknown"),
                    "confidence": data.get("confidence", "Unknown"),
                    "fx_source": fx_source,
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