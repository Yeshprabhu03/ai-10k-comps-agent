import yfinance as yf
ticker = yf.Ticker("WBD")
news = ticker.news
for n in news[:3]:
    print(n.get("title"))
    print(n.get("publisher"))
    print("---")
