import tweepy
import os
from datetime import date
from openai import OpenAI

# Load keys from GitHub Secrets
OPENAI_KEY = os.environ["OPENAI_KEY"]
X_API_KEY = os.environ["X_API_KEY"]
X_API_SECRET = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_SECRET = os.environ["X_ACCESS_SECRET"]

# Initialize OpenAI client
client = OpenAI(api_key=OPENAI_KEY)

def generate_article(voice, name):
    """
    Generate one political op-ed article in the style of the specified voice.
    voice = 'conservative' or 'progressive'
    name = columnist persona name
    """

    prompt = f"""
You are {name}, a political opinion columnist writing in a professional newspaper style.
Write a 2–4 paragraph op-ed article about today's political or economic news.
Perspective: {voice}.
Tone: thoughtful, analytical, structured, neutral toward groups.
Keep it under 900 characters and avoid targeted persuasion.
    """

    response = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7
    )

    return response.choices[0].message["content"].strip()


def post_to_x(text):
    """
    Posts the given text to X (Twitter) using Tweepy.
    """

    client_x = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_SECRET
    )

    client_x.create_tweet(text=text)


def main():
    today = date.today().strftime("%B %d, %Y")

    # Generate both articles
    conservative_article = generate_article("conservative", "Richard Hawthorne")
    progressive_article = generate_article("progressive", "Elena Marlowe")

    # Combined tweet content
    tweet = f"""Daily Political Commentary — {today}

🟦 Conservative — Richard Hawthorne:
{conservative_article}

🟥 Progressive — Elena Marlowe:
{progressive_article}
"""

    # Post to X
    post_to_x(tweet)


if __name__ == "__main__":
    main()
