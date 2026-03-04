import httpx
import asyncio
import urllib.parse
async def test():
    async with httpx.AsyncClient() as ac:
        req = await ac.get(f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote('Warner Bros. Discovery acquisitions')}&utf8=&format=json")
        res = req.json()
        print(res.keys())
        print([r['title'] for r in res['query']['search'][:3]])
asyncio.run(test())
