import os
import requests
from bs4 import BeautifulSoup
import yfinance as yf
import feedparser
from twilio.rest import Client
import pandas as pd
import numpy as np
import openai
import praw
import tweepy

# --- הגדרות API וסודות ---
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE = os.getenv("TWILIO_PHONE")
TARGET_PHONE = os.getenv("TARGET_PHONE")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = "investment_alert_bot/0.1"

TWITTER_BEARER_TOKEN = os.getenv("TWITTER_BEARER_TOKEN")

# --- אתחול קליינטים ---
client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
openai.api_key = OPENAI_API_KEY

reddit = praw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent=REDDIT_USER_AGENT
)

twitter_client = tweepy.Client(bearer_token=TWITTER_BEARER_TOKEN)

def send_sms(message):
    client.messages.create(body=message, from_=TWILIO_PHONE, to=TARGET_PHONE)
    print("Sent SMS:", message)

# --- פונקציות סטוק ודאטה ---

def get_rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def get_stock_data(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1mo")
        if len(hist) < 20:
            return None
        close = hist['Close']
        rsi = get_rsi(close)
        change_pct = ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100
        volume = hist['Volume'].iloc[-1]
        return {"ticker": ticker, "rsi": rsi, "change_pct": change_pct, "volume": volume}
    except Exception as e:
        print(f"Error fetching stock data for {ticker}: {e}")
        return None

def get_news(ticker, max_items=10):
    try:
        rss_url = f"https://news.google.com/rss/search?q={ticker}&hl=en-US&gl=US&ceid=US:en"
        feed = feedparser.parse(rss_url)
        entries = feed.entries[:max_items]
        return entries
    except Exception as e:
        print(f"Error fetching news for {ticker}: {e}")
        return []

# --- ניתוח סנטימנט מתקדם עם OpenAI ---
def analyze_sentiment_ai(news_items):
    if not news_items:
        return 0

    combined_text = "\n".join([item.title for item in news_items])
    prompt = (
        "Analyze the sentiment of the following financial news headlines. "
        "Return a sentiment score from -5 (very negative) to +5 (very positive).\n\n"
        f"{combined_text}\n\nSentiment score:"
    )
    try:
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=prompt,
            max_tokens=10,
            temperature=0,
            n=1,
            stop=["\n"]
        )
        score_text = response.choices[0].text.strip()
        score = float(score_text)
        print(f"OpenAI sentiment score: {score}")
        return score
    except Exception as e:
        print(f"Error in OpenAI sentiment analysis: {e}")
        return 0

# --- Reddit analysis ---
def get_reddit_mentions(ticker, limit=20):
    try:
        query = ticker
        subreddit = reddit.subreddit('stocks')
        posts = subreddit.search(query, limit=limit)
        count = 0
        positive = 0
        negative = 0
        for post in posts:
            count += 1
            title = post.title.lower()
            if any(word in title for word in ["buy", "bull", "moon", "long", "rocket"]):
                positive += 1
            if any(word in title for word in ["sell", "bear", "dump", "short", "crash"]):
                negative += 1
        score = positive - negative
        return {"mentions": count, "sentiment": score}
    except Exception as e:
        print(f"Error fetching Reddit data for {ticker}: {e}")
        return {"mentions": 0, "sentiment": 0}

# --- Twitter analysis ---
def get_twitter_mentions(ticker, limit=20):
    try:
        query = f"${ticker}"
        tweets = twitter_client.search_recent_tweets(query=query, max_results=limit)
        count = 0
        positive = 0
        negative = 0
        if tweets.data is None:
            return {"mentions": 0, "sentiment": 0}
        for tweet in tweets.data:
            text = tweet.text.lower()
            count += 1
            if any(word in text for word in ["buy", "bull", "moon", "long", "rocket"]):
                positive += 1
            if any(word in text for word in ["sell", "bear", "dump", "short", "crash"]):
                negative += 1
        score = positive - negative
        return {"mentions": count, "sentiment": score}
    except Exception as e:
        print(f"Error fetching Twitter data for {ticker}: {e}")
        return {"mentions": 0, "sentiment": 0}

def get_recent_13f_filings(count=50):
    try:
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=13F-HR&count={count}"
        headers = {'User-Agent': 'Mozilla/5.0 (InvestmentAlertBot)'}
        r = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(r.text, "html.parser")
        filings = []
        rows = soup.find_all('tr')[1:]
        for row in rows:
            cols = row.find_all('td')
            if len(cols) < 5:
                continue
            company = cols[1].text.strip()
            filings.append(company)
        return filings
    except Exception as e:
        print(f"Error fetching 13F filings: {e}")
        return []

def score_opportunity(stock_data, sentiment_ai_score, reddit_data, twitter_data, filings, ticker):
    score = 0

    # RSI
    if stock_data["rsi"] < 30:
        score += 4
    if stock_data["rsi"] > 70:
        score -= 3

    # שינוי מחיר
    if abs(stock_data["change_pct"]) >= 5:
        score += 5

    # נפח מסחר
    if stock_data["volume"] > 1_000_000:
        score += 1

    # סנטימנט AI
    if sentiment_ai_score > 2:
        score += 5
    elif sentiment_ai_score < -2:
        score -= 5

    # Reddit
    if reddit_data["mentions"] > 5:
        score += 2
    score += reddit_data["sentiment"]

    # Twitter
    if twitter_data["mentions"] > 5:
        score += 2
    score += twitter_data["sentiment"]

    # דיווחים 13F
    if ticker in filings:
        score += 4

    return score

# רשימת מניות S&P 500 לדוגמה (כמו קודם)
TICKERS = [
    "AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META", "BRK-B", "JPM", "V",
    "JNJ", "WMT", "UNH", "HD", "PG", "MA", "DIS", "BAC", "ADBE", "CMCSA",
    "NFLX", "PFE", "KO", "XOM", "CSCO", "VZ", "PEP", "INTC", "T", "CVX",
    "ABT", "CRM", "COST", "NKE", "MRK", "ORCL", "ACN", "MDT", "QCOM", "TXN",
    "LIN", "BMY", "LOW", "IBM", "MCD", "GE", "AMGN", "SBUX", "GILD", "UPS"
]

def run():
    print("=== Starting AI Advanced Investment Alert ===")
    filings = get_recent_13f_filings()

    for ticker in TICKERS:
        stock_data = get_stock_data(ticker)
        if not stock_data:
            continue

        news_items = get_news(ticker)
        sentiment_ai_score = analyze_sentiment_ai(news_items)
        reddit_data = get_reddit_mentions(ticker)
        twitter_data = get_twitter_mentions(ticker)

        score = score_opportunity(stock_data, sentiment_ai_score, reddit_data, twitter_data, filings, ticker)
        print(f"{ticker}: Score={score}, RSI={stock_data['rsi']:.1f}, Change={stock_data['change_pct']:.2f}%, AI Sentiment={sentiment_ai_score}, Reddit Sentiment={reddit_data['sentiment']}, Twitter Sentiment={twitter_data['sentiment']}")

        if score >= 8:  # סף גבוה יותר בהתחשב בניתוחים הרבים
            message = (
                f"🚀 AI Investment Alert: {ticker}\n"
                f"Score: {score}\n"
                f"RSI: {stock_data['rsi']:.1f}\n"
                f"Change: {stock_data['change_pct']:.2f}%\n"
                f"Volume: {stock_data['volume']}\n"
                f"AI Sentiment: {sentiment_ai_score}\n"
                f"Reddit Mentions: {reddit_data['mentions']} (Sentiment: {reddit_data['sentiment']})\n"
                f"Twitter Mentions: {twitter_data['mentions']} (Sentiment: {twitter_data['sentiment']})\n"
                f"Recent 13F filings: {'Yes' if ticker in filings else 'No'}\n"
                f"Top News:\n"
            )
            for i, news in enumerate(news_items[:3]):
                message += f"- {news.title}\n"
            send_sms(message)

    print("=== Finished AI Advanced Investment Alert ===")

if __name__ == "__main__":
    run()