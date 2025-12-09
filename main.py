import tweepy
import os
import json
import requests
from datetime import date
from openai import OpenAI
from pytrends.request import TrendReq

# NEW: import memory functions
from memory import init_qdrant, ensure_collection, store_article

# Load keys from GitHub Secrets
OPENAI_KEY = os.environ["OPENAI_KEY"]
X_API_KEY = os.environ["X_API_KEY"]
X_API_SECRET = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_SECRET = os.environ["X_ACCESS_SECRET"]

# NEW: Test Mode Flag
TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"

# NewsAPI key
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY")

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_KEY)


def load_personality(path):
    """Load a columnist's personality JSON file."""
    with open(path, "r") as f:
        return json.load(f)


def get_trending_political_topic():
    """Try Google Trends first; if it fails, fallback to NewsAPI."""

    # --- PRIMARY SOURCE: GOOGLE TRENDS ---
    try:
        print("Fetching topic from Google Trends…")

        pytrends = TrendReq(hl='en-US', tz=360)
        trending = pytrends.trending_searches(pn='united_states')
        topics = [str(t[0]) for t in trending.values.tolist()]

        political_keywords = [
            "elect", "presid", "biden", "trump", "congress", "congres",
            "senat", "house", "bill", "border", "policy", "supreme", "court",
            "immigra", "econom", "inflat", "ukraine", "gaza", "israel",
            "tax", "govern", "republic", "democ", "white house",
            "infrastructure"
        ]

        political_topics = [
            topic for topic in topics
            if any(keyword.lower() in topic.lower() for keyword in political_keywords)
        ]

        if political_topics:
            topic = political_topics[0]
            print("✔ Google Trends topic:", topic)
            return topic

        if topics:
            print("✔ Google Trends general topic:", topics[0])
            return topics[0]

    except Exception as e:
        print("⚠ Google Trends failed:", e)

    # --- FALLBACK SOURCE: NEWSAPI ---
    try:
        print("Fetching political headline from NewsAPI…")

        url = (
            "https://newsapi.org/v2/top-headlines?"
            f"category=politics&language=en&country=us&apiKey={NEWSAPI_KEY}"
        )

        response = requests.get(url)
        data = response.json()

        if "articles" in data and len(data["articles"]) > 0:
            headline = data["articles"][0]["title"]
            print("✔ NewsAPI topic:", headline)
            return headline

    except Exception as e:
        print("⚠ NewsAPI error:", e)

    # --- FINAL SAFETY FALLBACK ---
    print("⚠ Using final fallback topic.")
    return "current U.S. political developments"


def generate_neutral_summary(topic):
    """Generate a strictly neutral one-sentence summary."""

    prompt = f"""
Write exactly one sentence that provides a strictly neutral, factual summary 
of this trending political topic: {topic}. 
Do NOT express any opinion, emotion, speculation, or evaluation. 
Do NOT take a side. 
Keep it purely descriptive.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    return response.choices[0].message.content.strip()


def generate_article(voice, name, topic, personality):
    """Generate a spicy political op-ed, enhanced with personality memory."""

    personality_text = json.dumps(personality, indent=2)

    prompt = f"""
You are {name}, an established political opinion columnist. Here is your personality profile:
{personality_text}

Write a 2–4 paragraph op-ed article about this trending political topic: {topic}.
Perspective: {voice}.

Your tone should be assertive, bold, and provocative — offering strong opinions,
confident claims, pointed observations, and occasional rhetorical flair. You may explicitly 
name public political figures (e.g., the sitting President, former Presidents, major political leaders, Senators, Governors) 
and occasionally praise or criticize them when relevant, but keep your commentary analytical,
not targeted at specific demographic groups.

You are NOT neutral — you are an opinion writer with a clear ideological viewpoint — 
but you still maintain professionalism and avoid personal attacks or incitement. 
Keep commentary grounded in policy, leadership decisions, and public events.

Keep the article under 900 characters.
"""

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8
    )

    return response.choices[0].message.content.strip()


def post_to_x(text):
    """Posts the given text to X using Tweepy."""
    client_x = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_SECRET
    )
    client_x.create_tweet(text=text)


def main():
    today = date.today().strftime("%B %d, %Y")

    # Load personality seeds
    richard_personality = load_personality("personalities/richard.json")
    elena_personality = load_personality("personalities/elena.json")

    # 1. Get trending topic
    topic = get_trending_political_topic()

    # 2. Neutral summary
    summary = generate_neutral_summary(topic)

    # 3. Opinions
    conservative_article = generate_article(
        "conservative", "Richard Hawthorne", topic, richard_personality
    )
    progressive_article = generate_article(
        "progressive", "Elena Marlowe", topic, elena_personality
    )

    # 4. Store articles in Qdrant
    qdrant = init_qdrant()
    ensure_collection(qdrant)

    store_article(qdrant, "Richard Hawthorne", topic, conservative_article)
    store_article(qdrant, "Elena Marlowe", topic, progressive_article)

    # 5. Final tweet
    tweet = f"""Daily Political Commentary — {today}

🔥 Trending Topic: {topic}

📰 Summary:
{summary}

🦅 Conservative — Richard Hawthorne:
{conservative_article}

⚖️ Progressive — Elena Marlowe:
{progressive_article}
"""

    # 6. Post or skip if test mode
    if TEST_MODE:
        print("\n===== TEST MODE ACTIVE — SKIPPING POST TO X =====")
        print(tweet)
        print("=================================================\n")
    else:
        post_to_x(tweet)


if __name__ == "__main__":
    main()
