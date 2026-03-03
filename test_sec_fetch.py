import urllib.request
import json

req = urllib.request.Request(
    "https://www.sec.gov/files/company_tickers.json",
    headers={"User-Agent": "IB-Comps-Agent/1.0 (https://github.com/your-repo; contact@example.com)"}
)
try:
    with urllib.request.urlopen(req) as resp:
        print("Success:", len(json.loads(resp.read().decode())))
except Exception as e:
    print("Error:", e)
