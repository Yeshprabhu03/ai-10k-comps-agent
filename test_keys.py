import yfinance as yf
news = yf.Ticker("MSFT").news
if news:
    print(list(news[0].keys()))
