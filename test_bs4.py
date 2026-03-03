import urllib.request
import json
import yfinance as yf
from bs4 import BeautifulSoup

tick = "MSFT"
news = yf.Ticker(tick).news
if news:
    url = news[0]["link"]
    print(f"Fetching: {url}")
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        html = urllib.request.urlopen(req, timeout=10).read()
        soup = BeautifulSoup(html, "html.parser")
        text = " ".join([p.text for p in soup.find_all("p")])
        print(f"Scraped {len(text)} chars.")
    except Exception as e:
        print(f"Error scraping: {e}")
