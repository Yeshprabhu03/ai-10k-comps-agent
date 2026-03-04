import httpx
import asyncio

async def test():
    async with httpx.AsyncClient() as ac:
        try:
            # Let's try grabbing the Wikipedia "List of deepest M&A" or the Yahoo Finance profile
            resp = await ac.get("https://en.wikipedia.org/w/api.php?action=query&prop=extracts&exintro&titles=Warner_Bros._Discovery&format=json")
            print(resp.json()['query']['pages'])
        except Exception as e:
            print(e)
            
asyncio.run(test())
