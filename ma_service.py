import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from google import genai
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from urllib.parse import quote
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(title="IB Comps M&A Microservice", version="1.0")

class DealItem(BaseModel):
    deal_name: str
    target_company: str
    acquirer_company: str
    deal_value: str
    buy_side_advisors: str
    sell_side_advisors: str

class DealResponse(BaseModel):
    ticker: str
    deals: List[DealItem]
    status: str

@app.get("/")
def health_check():
    return {"status": "healthy", "service": "M&A Deal Extractor"}

@app.get("/api/v1/deals/{ticker}", response_model=DealResponse)
async def get_recent_ma_deals(ticker: str, api_key: str = None):
    try:
        # 1. First try deep Google SERP scraping for actual Investment Bank Advisors and Deal Values
        from googlesearch import search
        
        news_items = set()
        
        # We run two specific queries to guarantee we find the M&A Deal Value AND the involved Underwriters
        query_general = f"{ticker} \"merger\" OR \"acquisition\" \"deal value\""
        query_advisors = f"{ticker} merger acquisition \"financial advisor\" OR \"advised by\" OR \"investment bank\""
        
        try:
            # Fetch general M&A news
            for res in search(query_general, advanced=True, num_results=5, sleep_interval=2):
                if res.description and len(res.description) > 30:
                    news_items.add(f"Title: {res.title}\nSnippet: {res.description}")
                
            # Fetch Investment Banking Advisor specific news
            for res in search(query_advisors, advanced=True, num_results=5, sleep_interval=2):
                if res.description and len(res.description) > 30:
                    news_items.add(f"Title: {res.title}\nSnippet: {res.description}")
        except Exception as e:
            print(f"Google Rate Limit Hit. Falling back to DuckDuckGo: {e}")
            pass
            
        # 2. If Google failed or returned empty (HTTP 429), fallback to DuckDuckGo HTML scraping
        if not news_items:
            import urllib.parse
            from bs4 import BeautifulSoup
            import httpx
            import ssl
            import asyncio
            
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            query_val_ddg = urllib.parse.quote(f"{ticker} acquires acquired merger deal value billion")
            query_adv_ddg = urllib.parse.quote(f"{ticker} merger acquisition financial advisor investment bank advising")
            
            url_val = f"https://html.duckduckgo.com/html/?q={query_val_ddg}"
            url_adv = f"https://html.duckduckgo.com/html/?q={query_adv_ddg}"
            
            async with httpx.AsyncClient(verify=ctx) as ac:
                # Fetch both Deal Value and Advisor Context
                reqs = await asyncio.gather(
                    ac.get(url_val, timeout=10.0, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}),
                    ac.get(url_adv, timeout=10.0, headers={'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'})
                )
                
                for resp in reqs:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    for a in soup.find_all('a', class_='result__snippet'):
                        text = a.text.strip()
                        if text and len(text) > 30:
                            news_items.add(text)
                    for d in soup.find_all('div', class_='result__snippet'):
                        text = d.text.strip()
                        if text and len(text) > 30:
                            news_items.add(text)
                            
        news_items = list(news_items)
            
        if not news_items:
            return DealResponse(ticker=ticker, deals=[], status="No news found via Search APIs")
            
        combined_text = "\n---\n".join(news_items)
        
        prompt = f"""
        You are an elite Investment Banking analyst. Read the following recent financial news snippets regarding the company {ticker}.
        Identify any recent Mergers & Acquisitions (M&A) involving {ticker} or its close competitors.
        
        Extract the following structured data as a strict JSON array of objects. 
        Each object must have exactly these keys:
        - "deal_name": (string, e.g. "Microsoft acquires Activision")
        - "target_company": (string)
        - "acquirer_company": (string)
        - "deal_value": (string, e.g. "$68.7 Billion", or "Undisclosed")
        - "buy_side_advisors": (string, list the investment banks advising the acquirer, or "Not Mentioned")
        - "sell_side_advisors": (string, list the investment banks advising the target, or "Not Mentioned")
        
        If no M&A deals are found in the text, return an empty array [].
        Do NOT output markdown formatting like ```json, just the raw JSON array string.
        
        News Context:
        {combined_text}
        """
        
        import os
        from dotenv import load_dotenv
        load_dotenv()
        
        if not api_key:
            api_key = os.getenv("GOOGLE_API_KEY")
            
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        
        import json
        raw_text = response.text.strip()
        if raw_text.startswith("```json"):
            raw_text = raw_text[7:]
        if raw_text.startswith("```"):
            raw_text = raw_text[3:]
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
            
        deals_data = json.loads(raw_text.strip())
        
        deals = []
        for d in deals_data:
            deals.append(DealItem(**d))
            
        return DealResponse(ticker=ticker, deals=deals, status="Success")
        
    except Exception as e:
        print(f"Error extracting deals for {ticker}: {e}")
        return DealResponse(ticker=ticker, deals=[], status=f"Error: {str(e)}")

# To run: uvicorn ma_service:app --reload --port 8000
