import tweepy
import os
from datetime import date
from openai import OpenAI
from pytrends.request import TrendReq

# Load keys from GitHub Secrets
OPENAI_KEY = os.environ["OPENAI_KEY"]
X_API_KEY = os.environ["X_API_KEY"]
X_API_SECRET = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_SECRET = os.environ["X_ACCESS_SECRET"]

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_KEY)


def get_trending_political_topic():
    """Fetch trending topics from Google Trends and filter for political relevance."""

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
        return political_topics[0]

    return "a major political issue trending today"


def generate_neutral_summary(topic):
    """Generate a short, strictly neutral one-sentence summary of the topic."""

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


def generate_article(voice, name, topic):
    """Generate a spicy political op-ed from a left or right perspective."""

    prompt = f"""
You are {name}, a sharp and opinionated political columnist writing in a punchy newspaper style.
Write a 2–4 paragraph op-ed article about this trending political topic: {topic}.
Perspective: {voice}.

Your tone should be more assertive, bold, and provocative — offering strong opinions,
confident claims, pointed observations, and occasional rhetorical flair. You may explicitly 
name public political figures (e.g., President Biden, former President Trump, Senators, Governors) 
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
    """Posts the given text to X (Twitter) using Tweepy."""

    client_x = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_SECRET
    )

    client_x.create_tweet(text=text)


def main():
    today = date.today().strftime("%B %d, %Y")

    # 1. Get trending topic
    topic = get_trending_political_topic()

    # 2. Neutral summary
    summary = generate_neutral_summary(topic)

    # 3. Opinion pieces
    conservative_article = generate_article(
        "conservative", "Richard Hawthorne", topic
    )

    progressive_article = generate_article(
        "progressive", "Elena Marlowe", topic
    )

    # 4. Final tweet text
    tweet = f"""Daily Political Commentary — {today}

🔥 Trending Topic: {topic}

📰 Summary:
{summary}

🟦 Conservative — Richard Hawthorne:
{conservative_article}

🟥 Progressive — Elena Marlowe:
{progressive_article}
"""

    # 5. Post to X
    post_to_x(tweet)


if __name__ == "__main__":
    main()
