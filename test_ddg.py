import httpx
import asyncio
import urllib.parse
from bs4 import BeautifulSoup
import re

async def test():
    query = "Warner Bros Discovery mergers acquisitions advisory firm deal value"
    url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
    
    async with httpx.AsyncClient(headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}) as ac:
        resp = await ac.get(url)
        soup = BeautifulSoup(resp.text, 'html.parser')
        snippets = []
        for a in soup.find_all('a', class_='result__snippet'):
            snippets.append(a.text)
        
        print("\n---\n".join(snippets))

asyncio.run(test())
