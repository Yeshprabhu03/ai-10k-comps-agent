import yfinance as yf
stock = yf.Ticker("NVDA")
f_info = stock.fast_info
print("market_cap using .get:", getattr(f_info, "get", lambda x, y: "No get method")("market_cap", 0))
print("market_cap using property:", f_info.market_cap)
