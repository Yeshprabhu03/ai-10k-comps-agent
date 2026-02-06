import os
import json
import time
import pandas as pd
from dotenv import load_dotenv
from google import genai
from edgar import *

# 1. Setup
load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
# Using your Fordham identity for SEC access
set_identity("Yeshwanth your-email@fordham.edu")

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
                
                # Access the financials object directly to get the cleanest string
                try:
                    # edgartools: calling income_statement() returns the report object
                    income_stmt = f_obj.financials.income_statement()
                    financial_summary = str(income_stmt)
                except:
                    # Fallback for different labeling or foreign filers
                    try:
                        income_stmt = f_obj.financials.statements_of_operations()
                        financial_summary = str(income_stmt)
                    except:
                        financial_summary = str(f_obj.financials)

                # AI Prompt: Explicitly state that values are in MILLIONS
                prompt = (
                    f"Analyze {ticker} for the latest FY. VALUES ARE IN MILLIONS. "
                    "Extract 'Total net sales' (Revenue), 'Net income', and 'Operating income'. "
                    "Return ONLY JSON with numbers (e.g., 416161). "
                    "Format: {'revenue': 416161, 'net_income': 93736, 'operating_income': 114301, 'dep_amort': 11046}"
                    f"\nData:\n{financial_summary}"
                )
                
                response = client.models.generate_content(
                    model="gemini-2.0-flash", 
                    contents=prompt
                )
                
                raw_text = response.text.strip().replace("```json", "").replace("```", "")
                data = json.loads(raw_text)
                
                # Logic to scale millions into absolute USD
                def clean_num(key):
                    val = data.get(key, 0)
                    if val is None or str(val).lower() == 'none': 
                        return 0.0
                    num = float(str(val).replace(',', '').replace('$', ''))
                    # Standard SEC reporting is in Millions; scale to Dollars
                    return num * 1_000_000

                # IB Methodology: EBITDA = Operating Income + D&A
                revenue = clean_num('revenue')
                net_inc = clean_num('net_income')
                op_inc = clean_num('operating_income')
                da = clean_num('dep_amort')
                
                results.append({
                    'ticker': ticker,
                    'filing_date': filing_date,
                    'revenue': revenue,
                    'net_income': net_inc,
                    'ebitda': op_inc + da,
                    'net_margin_%': (net_inc / revenue * 100) if revenue > 0 else 0
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