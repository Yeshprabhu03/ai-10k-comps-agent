import os
import asyncio
from ma_service import get_recent_ma_deals
from dotenv import load_dotenv

load_dotenv()
async def test():
    key = os.getenv("GOOGLE_API_KEY")
    res = await get_recent_ma_deals("WBD", api_key=key)
    print(res.model_dump_json())

asyncio.run(test())
