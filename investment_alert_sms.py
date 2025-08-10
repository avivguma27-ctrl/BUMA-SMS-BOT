import os
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import feedparser
from twilio.rest import Client

# Twilio setup
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE = os.getenv("TWILIO_PHONE")
TARGET_PHONE = os.getenv("TARGET_PHONE")

client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)

def send_sms(message):
    msg = client.messages.create(body=message, from_=TWILIO_PHONE, to=TARGET_PHONE)
    print(f"Sent SMS: {message}")

def get_stock_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="2d")
        if len(hist) < 2:
            return None
        today_close = hist['Close'].iloc[-1]
        yesterday_close = hist['Close'].iloc[-2]
        change_pct = ((today_close - yesterday_close) / yesterday_close) * 100
        return change_pct
    except Exception as e:
        print(f"Error getting price for {ticker}: {e}")
        return None

def get_google_news_count(ticker):
    try:
        rss_url = f"https://news.google.com/rss/search?q={ticker}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(rss_url)
        return len(feed.entries)
    except Exception as e:
        print(f"Error getting news for {ticker}: {e}")
        return 0

def score_opportunity(change_pct, news_count):
    score = 0
    if change_pct is not None and abs(change_pct) > 5:
        score += 3
    if news_count > 3:
        score += news_count
    return score

# רשימת טיקרים לדוגמה (מניות גדולות ונפוצות)
TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "BRK-B", "JPM", "V",
    "JNJ", "WMT", "UNH", "HD", "PG", "MA", "DIS", "BAC", "ADBE", "CMCSA",
    "NFLX", "PFE", "KO", "XOM", "CSCO", "VZ", "PEP", "INTC", "T", "CVX",
    "ABT", "CRM", "COST", "NKE", "MRK", "ORCL", "ACN", "MDT", "QCOM", "TXN",
    "LIN", "BMY", "LOW", "IBM", "MCD", "GE", "AMGN", "SBUX", "GILD", "UPS"
]

def run():
    print("=== Starting investment alert run ===")
    for ticker in TICKERS:
        print(f"Checking {ticker}...")
        change_pct = get_stock_price(ticker)
        news_count = get_google_news_count(ticker)
        score = score_opportunity(change_pct, news_count)

        print(f"{ticker}: Change={change_pct}, News count={news_count}, Score={score}")

        if score >= 5:
            msg = f"📈 Investment Alert for {ticker}:\nChange: {change_pct:.2f}%\nNews Items: {news_count}\nScore: {score}"
            send_sms(msg)
    print("=== Finished run ===")

if __name__ == "__main__":
    run()