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
        # Use DuckDuckGo HTML search for deeper snippets than RSS
        import urllib.parse
        query = urllib.parse.quote(f"{ticker} mergers acquisitions advisory firm deal value")
        url = f"https://html.duckduckgo.com/html/?q={query}"
        
        from bs4 import BeautifulSoup
        import httpx
        import ssl
        
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        async with httpx.AsyncClient(verify=ctx) as ac:
            resp = await ac.get(url, timeout=15.0, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Safari/537.36'})
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            news_items = []
            for a in soup.find_all('a', class_='result__snippet'):
                text = a.text.strip()
                if text:
                    news_items.append(text)
                    
            if not news_items:
                # Fallback to general snippets if 'a' tags fail
                for d in soup.find_all('div', class_='result__snippet'):
                    text = d.text.strip()
                    if text:
                        news_items.append(text)
        
        if not news_items:
            return DealResponse(ticker=ticker, deals=[], status="No news found")
            
        # Only keep top 15 snippets to avoid token explosion
        combined_text = "\n---\n".join(news_items[:15])
        
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
