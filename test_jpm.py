import pandas as pd
from comps_agent import get_all_sec_tickers

sec_list = get_all_sec_tickers()
# 1. Test dict lookup to see if JPM is even in the SEC list
sec_dict = dict(sec_list)
print(f"JPM in SEC dict? {'JPM' in sec_dict}")
print(f"JPM value: {sec_dict.get('JPM')}")

# 2. Test pandas datetime conversion
ts = 1770940800000 # Example from screenshot (JPM)
try:
    print(f"Convert ms timestamp: {pd.to_datetime(ts, unit='ms').strftime('%Y-%m-%d')}")
except Exception as e:
    print(f"Convert ms failed: {e}")

try:
    print(f"Convert s timestamp: {pd.to_datetime(ts, unit='s').strftime('%Y-%m-%d')}")
except Exception as e:
    print(f"Convert s failed: {e}")
