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

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

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
def get_recent_ma_deals(ticker: str):
    try:
        # Build Google News RSS query for M&A
        query = quote(f"{ticker} (merger OR acquisition OR buyout OR advised by)")
        url = f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
        
        req = Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        
        with urlopen(req, timeout=10, context=ctx) as resp:
            xml_data = resp.read()
        
        # Parse RSS
        root = ET.fromstring(xml_data)
        news_items = []
        for item in root.findall('.//item')[:10]:  # Top 10 articles
            title = item.find('title').text if item.find('title') is not None else ""
            desc = item.find('description').text if item.find('description') is not None else ""
            pub_date = item.find('pubDate').text if item.find('pubDate') is not None else ""
            news_items.append(f"Title: {title}\nDate: {pub_date}\nSummary: {desc}\n")
        
        if not news_items:
            return DealResponse(ticker=ticker, deals=[], status="No news found")
            
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
