import tweepy
import os
import json
import requests
import urllib.parse
from datetime import date
from openai import OpenAI

from memory import init_qdrant, ensure_collection, store_article

# -----------------------
# ENV / CONFIG
# -----------------------
OPENAI_KEY = os.environ["OPENAI_KEY"]
X_API_KEY = os.environ["X_API_KEY"]
X_API_SECRET = os.environ["X_API_SECRET"]
X_ACCESS_TOKEN = os.environ["X_ACCESS_TOKEN"]
X_ACCESS_SECRET = os.environ["X_ACCESS_SECRET"]
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY")

TEST_MODE = os.environ.get("TEST_MODE", "false").lower() == "true"

client = OpenAI(api_key=OPENAI_KEY)

# Hard truth grounding to avoid outdated assumptions
CURRENT_FACTS = """
You must follow these UPDATED REAL-WORLD FACTS, overriding outdated knowledge:

- The current U.S. President is Donald J. Trump (2nd nonconsecutive term: 2025–2029).
- Joe Biden is the former U.S. President (2021–2025).
- If you refer to "the President", "the administration", or current executive policy, you MUST mean President Trump and his administration.
- Do NOT describe Biden as the current president.
- Do NOT describe Trump as the former president.
- If Wikipedia factual notes contradict your memory, trust Wikipedia instead.
"""


def load_personality(path: str) -> dict:
    with open(path, "r") as f:
        return json.load(f)


# -----------------------
# 1) TOPIC (NewsAPI)
# -----------------------
def get_trending_political_topic() -> str:
    print("Fetching U.S. headlines from NewsAPI…")

    if not NEWSAPI_KEY:
        print("⚠ NEWSAPI_KEY missing — using fallback topic.")
        return "current U.S. political developments"

    try:
        url = (
            "https://newsapi.org/v2/top-headlines?"
            f"language=en&country=us&apiKey={NEWSAPI_KEY}"
        )
        r = requests.get(url, timeout=10)
        data = r.json()

        political_keywords = [
            "Biden", "Trump", "election", "Senate", "Congress",
            "Republican", "Democrat", "policy", "White House",
            "Governor", "immigration", "border", "Supreme Court",
            "bill", "tax", "Ukraine", "Gaza", "Israel", "NATO",
            "China", "diplomatic"
        ]

        for article in data.get("articles", []):
            title = article.get("title") or ""
            if any(k.lower() in title.lower() for k in political_keywords):
                print("✔ Political topic from NewsAPI:", title)
                return title

        # fallback: first headline
        articles = data.get("articles", [])
        if articles:
            fallback = articles[0].get("title") or "current U.S. political developments"
            print("⚠ No political match — using first headline:", fallback)
            return fallback

    except Exception as e:
        print("⚠ NewsAPI error:", e)

    return "current U.S. political developments"


# -----------------------
# 2) Wikipedia factual context
# -----------------------
def get_wikipedia_context(topic: str, max_pages: int = 3) -> str:
    try:
        search_url = "https://en.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": topic,
            "format": "json",
            "srlimit": max_pages,
        }
        headers = {
            "User-Agent": "politicalopinionist-bot/1.0 (contact: example@example.com)"
        }

        resp = requests.get(search_url, params=params, headers=headers, timeout=10)
        data = resp.json()
        results = data.get("query", {}).get("search", [])

        if not results:
            print("⚠ No Wikipedia search results.")
            return ""

        bullets = []
        for item in results:
            title = item.get("title")
            if not title:
                continue

            encoded = urllib.parse.quote(title.replace(" ", "_"))
            summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
            s_resp = requests.get(summary_url, headers=headers, timeout=10)
            if s_resp.status_code != 200:
                continue

            extract = (s_resp.json().get("extract") or "").strip()
            if not extract:
                continue

            if len(extract) > 420:
                extract = extract[:417] + "..."

            bullets.append(f"- {title}: {extract}")

        context = "\n".join(bullets[:max_pages])
        if context:
            print("✔ Wikipedia context fetched.")
        return context

    except Exception as e:
        print("⚠ Wikipedia error:", e)
        return ""


# -----------------------
# 3) Neutral summary
# -----------------------
def generate_neutral_summary(topic: str, wiki_context: str) -> str:
    wiki_block = f"\nWikipedia factual notes:\n{wiki_context}\n" if wiki_context else ""
    prompt = f"""
You are a strictly neutral political summarizer.

Topic: {topic}
{wiki_block}

Write exactly one sentence that is purely factual.
No opinions, no bias, no speculation.
"""
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()


# -----------------------
# 4) Long op-eds (store in Qdrant)
# -----------------------
def generate_long_oped(voice: str, name: str, topic: str, personality: dict, wiki_context: str) -> str:
    personality_text = json.dumps(personality, indent=2)
    wiki_block = (
        f"Factual notes from Wikipedia (treat as truth):\n{wiki_context}\n"
        if wiki_context else
        "If you are unsure of a fact, do not guess—stay general.\n"
    )

    prompt = f"""
You are {name}, a political opinion columnist. Here is your personality:
{personality_text}

MANDATORY FACTUAL REALITY:
{CURRENT_FACTS}

{wiki_block}

Write a 2–4 paragraph op-ed on: {topic}
Perspective: {voice}

Rules:
- Keep under 900 characters
- Opinionated but policy-focused and analytical
- May praise/criticize public figures
- No personal attacks or incitement
- Avoid claims you can't support; if unsure, phrase cautiously
"""
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
    )
    return resp.choices[0].message.content.strip()


# -----------------------
# 5) Tweet takes (publish on X)
# -----------------------
def generate_tweet_take(voice: str, name: str, topic: str, personality: dict, wiki_context: str) -> str:
    personality_text = json.dumps(personality, indent=2)
    wiki_block = (
        f"Factual notes from Wikipedia (treat as truth):\n{wiki_context}\n"
        if wiki_context else
        "If you are unsure of a fact, do not guess—stay general.\n"
    )

    prompt = f"""
You are {name}. Here is your personality:
{personality_text}

MANDATORY FACTUAL REALITY:
{CURRENT_FACTS}

{wiki_block}

Write ONE tweet about: {topic}
Perspective: {voice}

Hard constraints:
- Max 260 characters (leave room for emojis/formatting)
- Single paragraph
- One main argument + one supporting point
- Punchy and readable for X (not a newspaper op-ed)
- No hashtags unless absolutely natural
- No personal attacks or incitement
Return ONLY the tweet text.
"""
    resp = client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.8,
    )
    tweet = resp.choices[0].message.content.strip()
    return tweet


# -----------------------
# Posting
# -----------------------
def post_to_x(text: str) -> None:
    client_x = tweepy.Client(
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_SECRET,
    )
    client_x.create_tweet(text=text)


def main():
    today = date.today().strftime("%B %d, %Y")

    richard = load_personality("personalities/richard.json")
    elena = load_personality("personalities/elena.json")

    # 1) Topic
    topic = get_trending_political_topic()

    # 2) Wikipedia context (fresh daily)
    wiki_context = get_wikipedia_context(topic)

    # 3) Neutral summary
    summary = generate_neutral_summary(topic, wiki_context)

    # 4) Long op-eds (for memory)
    richard_oped = generate_long_oped("conservative", "Richard Hawthorne", topic, richard, wiki_context)
    elena_oped = generate_long_oped("progressive", "Elena Marlowe", topic, elena, wiki_context)

    # 5) Tweets (for publishing)
    richard_tweet = generate_tweet_take("conservative", "Richard Hawthorne", topic, richard, wiki_context)
    elena_tweet = generate_tweet_take("progressive", "Elena Marlowe", topic, elena, wiki_context)

    # 6) Store FULL CONTEXT in Qdrant (write-only, no retrieval)
    qdrant = init_qdrant()
    ensure_collection(qdrant)

    if wiki_context:
        store_article(qdrant, "CONTEXT_WIKIPEDIA", topic, wiki_context)
    store_article(qdrant, "SUMMARY_NEUTRAL", topic, summary)

    store_article(qdrant, "OPED_Richard Hawthorne", topic, richard_oped)
    store_article(qdrant, "OPED_Elena Marlowe", topic, elena_oped)

    store_article(qdrant, "TWEET_Richard Hawthorne", topic, richard_tweet)
    store_article(qdrant, "TWEET_Elena Marlowe", topic, elena_tweet)

    # 7) Compose X post (tweet-friendly)
    post_text = f"""Daily Political Takes — {today}

🔥 Topic: {topic}

📰 Summary: {summary}

🦅 Richard:
{richard_tweet}

⚖️ Elena:
{elena_tweet}
"""

    if TEST_MODE:
        print("\n===== TEST MODE ACTIVE — SKIPPING POST TO X =====\n")
        print(post_text)
        print("\n===============================================\n")
    else:
        post_to_x(post_text)


if __name__ == "__main__":
    main()
